import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import 'package:mealio/features/nutrition/presentation/nutrition_setup_controller.dart';
import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  late FakeNutritionRepository repo;
  late FakeSecureStorageService storage;
  late NutritionSetupController controller;
  setUp(() {
    repo = FakeNutritionRepository(json: nutritionJson(full: true));
    storage = FakeSecureStorageService(
      accessToken: 'synthetic-a',
      refreshToken: 'synthetic-r',
    );
    controller = NutritionSetupController(
      repository: repo,
      storage: storage,
      isAuthenticated: () => true,
    );
  });
  tearDown(() => controller.dispose());
  Future<void> toStep(int step) async {
    await controller.load();
    while (controller.step < step) {
      expect(await controller.save(), NutritionSaveResult.advanced);
    }
  }

  NutritionCalculated estimate([int calories = 3204]) => NutritionCalculated(
    '2026-10-04',
    NutritionTargets(calories: calories, protein: 160, carbs: 400, fat: 107),
    {for (final f in NutritionField.values) f: repo.json[f.wireName] as String},
  );

  test(
    'food only changed fields, overlaps, unrestricted lists and custom diet survive',
    () async {
      repo.json['diet_type'] = 'custom diet';
      await toStep(3);
      final likes = ['synthetic-allergen', 'synthetic-allergen', 'x' * 101];
      controller.editIngredients(PreferenceList.likes, likes);
      controller.editIngredients(PreferenceList.dislikes, ['new dislike']);
      await controller.save();
      expect(repo.patches.single, {
        'liked_ingredients': likes,
        'disliked_ingredients': ['new dislike'],
      });
      expect(repo.json['diet_type'], 'custom diet');
      expect(repo.json['allergies'], ['synthetic-allergen']);
      expect(repo.json['daily_calories_target'], 2400);
      controller.back();
      controller.editPreference(PreferenceField.diet, '');
      controller.editIngredients(PreferenceList.likes, []);
      await controller.save();
      expect(repo.patches.last, {'diet_type': null, 'liked_ingredients': []});
    },
  );
  test(
    'budget exact pair, invalid precision, deliberate clears; no empty PATCH',
    () async {
      await toStep(4);
      expect(repo.patches, isEmpty);
      controller.editPreference(PreferenceField.budgetAmount, '50,125');
      expect(await controller.save(), NutritionSaveResult.rejected);
      expect(repo.patches, isEmpty);
      controller.editPreference(PreferenceField.budgetAmount, '50,12');
      await controller.save();
      expect(repo.patches.single, {
        'weekly_food_budget_amount': '50.12',
        'budget_currency': 'EUR',
      });
      controller.back();
      controller.editPreference(PreferenceField.budgetAmount, '');
      expect(await controller.save(), NutritionSaveResult.rejected);
      controller.editPreference(PreferenceField.currency, '');
      controller.editPreference(PreferenceField.cookingTime, '');
      await controller.save();
      expect(repo.patches.last, {
        'weekly_food_budget_amount': null,
        'budget_currency': null,
        'max_cooking_time_minutes': null,
      });
    },
  );
  test(
    'save another step does not erase dirty preferences; Back/reopen distinction',
    () async {
      await toStep(4);
      controller.editPreference(PreferenceField.budgetAmount, '50,12');
      controller.back();
      controller.editIngredients(PreferenceList.likes, ['rice']);
      await controller.save();
      expect(controller.preferenceInput(PreferenceField.budgetAmount), '50,12');
      expect(controller.dirty, isTrue);
      final next = NutritionSetupController(
        repository: repo,
        storage: storage,
        isAuthenticated: () => true,
      );
      addTearDown(next.dispose);
      await next.load();
      expect(next.step, 0);
      expect(next.ingredients(PreferenceList.likes), ['rice']);
      expect(next.preferenceInput(PreferenceField.budgetAmount), '80.00');
      expect(next.calculation, isNull);
    },
  );
  test(
    'partial manual targets default preserve with no mutation; explicit adoption writes four shown ints',
    () async {
      await toStep(5);
      await controller.calculate(now: DateTime.utc(2026, 10, 4));
      expect(controller.useEstimate, isFalse);
      expect(controller.targets.carbs, isNull);
      expect(
        await controller.confirm(),
        NutritionSaveResult.finishedWithoutWrite,
      );
      expect(repo.patches, isEmpty);
      controller.selectEstimate(true);
      expect(await controller.confirm(), NutritionSaveResult.targetsApplied);
      expect(repo.patches.single, {
        'daily_calories_target': 3204,
        'daily_protein_target_g': 160,
        'daily_carbs_target_g': 400,
        'daily_fat_target_g': 107,
      });
      expect(repo.calculations, 1);
    },
  );
  test(
    'no targets means explicit confirm saves displayed estimate, never calculate itself',
    () async {
      for (final key in [
        'daily_calories_target',
        'daily_protein_target_g',
        'daily_carbs_target_g',
        'daily_fat_target_g',
      ]) {
        repo.json[key] = null;
      }
      await toStep(5);
      expect(await controller.confirm(), NutritionSaveResult.rejected);
      await controller.calculate();
      expect(repo.patches, isEmpty);
      expect(await controller.confirm(), NutritionSaveResult.targetsApplied);
      expect(repo.patches.single.length, 4);
    },
  );
  test(
    'all six formula edits invalidate estimate/selection, save before calculate',
    () async {
      await toStep(5);
      for (final f in NutritionField.values) {
        await controller.calculate();
        controller.selectEstimate(true);
        controller.edit(f, '${controller.input(f)} ');
        expect(controller.calculation, isNull);
        expect(controller.useEstimate, isFalse);
        controller.edit(f, repo.json[f.wireName] as String);
      }
      controller.edit(NutritionField.weight, '72.00');
      final calls = repo.calculations;
      await controller.calculate();
      expect(repo.calculations, calls);
      expect(await controller.confirm(), NutritionSaveResult.rejected);
      while (controller.step > 1) {
        controller.back();
      }
      await controller.save();
      await toStep(5);
      await controller.calculate();
      expect(controller.calculation, isA<NutritionCalculated>());
    },
  );
  for (final fails in [false, true]) {
    test(
      'older same-lifetime calculation ${fails ? 'failure' : 'success'} cannot override newer generation',
      () async {
        await toStep(5);
        final old = Completer<NutritionCalculation>();
        repo.calculateHandler = (_) => old.future;
        final pending = controller.calculate();
        await controller.calculate();
        expect(repo.calculations, 1);
        controller.edit(NutritionField.goal, 'gain_weight');
        controller.edit(NutritionField.goal, 'maintain');
        repo.calculateHandler = (_) async => estimate(3300);
        await controller.calculate();
        if (fails) {
          old.completeError(StateError('synthetic'));
        } else {
          old.complete(estimate());
        }
        await pending;
        expect(
          (controller.calculation as NutritionCalculated).targets.calories,
          3300,
        );
        expect(controller.failure, isNull);
      },
    );
  }
  test(
    'mismatching server used_inputs is not labelled as current draft',
    () async {
      await toStep(5);
      repo.calculateHandler = (_) async => NutritionCalculated(
        '2026-10-04',
        estimate().targets,
        {...estimate().usedInputs, NutritionField.weight: '99.00'},
      );
      await controller.calculate();
      expect(controller.calculation, isNull);
      expect(controller.failure?.type, NutritionFailureType.unexpected);
    },
  );
  test(
    'unsupported age18 W4 profile and incomplete keep saved targets; no fake estimate',
    () async {
      repo.json['birth_date'] = '2008-10-04';
      await toStep(5);
      for (final result in [
        NutritionUnsupported('2026-10-04', [NutritionUnsupportedReason.age]),
        NutritionIncomplete('2026-10-04', [NutritionField.weight]),
      ]) {
        repo.calculateHandler = (_) async => result;
        await controller.calculate(now: DateTime.utc(2026, 10, 4));
        expect(controller.calculation, same(result));
        controller.selectEstimate(true);
        expect(controller.useEstimate, isFalse);
        expect(controller.targets.calories, 2400);
        expect(
          await controller.confirm(),
          NutritionSaveResult.finishedWithoutWrite,
        );
        expect(repo.patches, isEmpty);
      }
    },
  );
  test(
    'failed confirm retry retains shown values, suppresses duplicates and navigation during write',
    () async {
      await toStep(5);
      await controller.calculate();
      controller.selectEstimate(true);
      final pending = Completer<NutritionProfile>();
      repo.saveHandler = (_) => pending.future;
      final operation = controller.confirm();
      expect(await controller.confirm(), NutritionSaveResult.rejected);
      controller.back();
      controller.edit(NutritionField.weight, '99.00');
      expect(controller.step, 5);
      expect(controller.input(NutritionField.weight), '70.25');
      pending.completeError(
        const NutritionFailure(NutritionFailureType.connection),
      );
      expect(await operation, NutritionSaveResult.rejected);
      expect(controller.calculation, isA<NutritionCalculated>());
      repo.saveHandler = null;
      expect(await controller.confirm(), NutritionSaveResult.targetsApplied);
      expect(repo.patches, hasLength(2));
      expect(repo.patches[0], repo.patches[1]);
      expect(repo.calculations, 1);
    },
  );
  for (final action in ['calculate', 'confirm']) {
    for (final fails in [false, true]) {
      for (final transition in ['A→B', 'A→A', 'dispose']) {
        test(
          '$action late $fails after $transition never publishes or retries',
          () async {
            await toStep(5);
            final calc = Completer<NutritionCalculation>();
            final save = Completer<NutritionProfile>();
            final snapshot = estimate();
            final Future<Object?> pending;
            if (action == 'calculate') {
              repo.calculateHandler = (_) => calc.future;
              pending = controller.calculate();
            } else {
              await controller.calculate();
              controller.selectEstimate(true);
              repo.saveHandler = (_) => save.future;
              pending = controller.confirm();
            }
            if (transition == 'dispose') {
              controller.dispose();
              // Replace the variable so tearDown only disposes the new instance.
            } else {
              await storage.writeTokenPair(
                AuthTokenPair(
                  accessToken: transition == 'A→A'
                      ? 'synthetic-a'
                      : 'synthetic-b',
                  refreshToken: 'synthetic-new',
                ),
              );
              controller.checkOwnership();
            }
            final old = controller;
            controller = NutritionSetupController(
              repository: FakeNutritionRepository(
                json: nutritionJson(full: true),
              ),
              storage: storage,
              isAuthenticated: () => true,
            );
            await controller.load();
            controller.editPreference(PreferenceField.diet, 'new draft');
            if (action == 'calculate') {
              if (fails) {
                calc.completeError(StateError('synthetic'));
              } else {
                calc.complete(snapshot);
              }
            } else {
              if (fails) {
                save.completeError(StateError('synthetic'));
              } else {
                save.complete(NutritionProfile.fromJson(nutritionJson()));
              }
            }
            final result = await pending;
            if (action == 'confirm') {
              expect(result, NutritionSaveResult.stale);
            }
            expect(old.calculation, isNull);
            expect(old.failure, isNull);
            expect(old.useEstimate, isFalse);
            await old.calculate();
            expect(await old.confirm(), NutritionSaveResult.stale);
            expect(
              controller.preferenceInput(PreferenceField.diet),
              'new draft',
            );
            expect(controller.step, 0);
            expect(controller.failure, isNull);
            if (transition != 'dispose') {
              old.dispose();
            }
          },
        );
      }
    }
  }
  test(
    'same-lifetime refresh retains estimate selection and dirty preferences',
    () async {
      await toStep(5);
      await controller.calculate();
      final shown = controller.calculation;
      controller.selectEstimate(true);
      controller.editPreference(PreferenceField.diet, 'draft');
      await storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: 'synthetic-r',
        pair: const AuthTokenPair(
          accessToken: 'synthetic-rotated',
          refreshToken: 'synthetic-rotated-r',
        ),
      );
      expect(controller.checkOwnership(), isTrue);
      expect(controller.calculation, same(shown));
      expect(controller.useEstimate, isTrue);
      expect(controller.preferenceInput(PreferenceField.diet), 'draft');
    },
  );
}

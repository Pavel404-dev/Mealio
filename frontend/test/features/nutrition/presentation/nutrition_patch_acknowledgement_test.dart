import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/presentation/nutrition_setup_controller.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

class _Scenario {
  const _Scenario(this.name, this.step, this.edit, this.patch);
  final String name;
  final int step;
  final void Function(NutritionSetupController) edit;
  final Map<String, Object?> patch;
}

void main() {
  final scenarios = [
    _Scenario('goal', 0, (c) => c.edit(NutritionField.goal, 'gain_weight'), {
      'goal': 'gain_weight',
    }),
    _Scenario(
      'body',
      1,
      (c) {
        c.edit(NutritionField.sex, 'male');
        c.edit(NutritionField.birthDate, '2000-01-02');
        c.edit(NutritionField.height, '181,0');
        c.edit(NutritionField.weight, '81,20');
      },
      {
        'sex': 'male',
        'birth_date': '2000-01-02',
        'height_cm': '181.0',
        'weight_kg': '81.20',
      },
    ),
    _Scenario(
      'activity',
      2,
      (c) => c.edit(NutritionField.activity, 'extra_active'),
      {'activity_level': 'extra_active'},
    ),
    _Scenario(
      'food',
      3,
      (c) {
        c.editPreference(PreferenceField.diet, ' custom diet ');
        for (final field in PreferenceList.values) {
          c.editIngredients(field, [' rice ', 'beans', 'rice', '']);
        }
      },
      {
        'diet_type': 'custom diet',
        'allergies': ['rice', 'beans', 'rice'],
        'liked_ingredients': ['rice', 'beans', 'rice'],
        'disliked_ingredients': ['rice', 'beans', 'rice'],
      },
    ),
    _Scenario(
      'practical',
      4,
      (c) {
        c.editPreference(PreferenceField.cookingTime, '030');
        c.editPreference(PreferenceField.budgetAmount, '50,12');
        c.editPreference(PreferenceField.currency, 'usd');
      },
      {
        'max_cooking_time_minutes': 30,
        'weekly_food_budget_amount': '50.12',
        'budget_currency': 'USD',
      },
    ),
    _Scenario(
      'clear food',
      3,
      (c) {
        c.editPreference(PreferenceField.diet, '');
        for (final field in PreferenceList.values) {
          c.editIngredients(field, []);
        }
      },
      {
        'diet_type': null,
        'allergies': <String>[],
        'liked_ingredients': <String>[],
        'disliked_ingredients': <String>[],
      },
    ),
    _Scenario(
      'clear practical',
      4,
      (c) {
        for (final field in [
          PreferenceField.cookingTime,
          PreferenceField.budgetAmount,
          PreferenceField.currency,
        ]) {
          c.editPreference(field, '');
        }
      },
      {
        'max_cooking_time_minutes': null,
        'weekly_food_budget_amount': null,
        'budget_currency': null,
      },
    ),
  ];
  late FakeNutritionRepository repo;
  late FakeSecureStorageService storage;
  late NutritionSetupController controller;
  late Map<String, dynamic> initial;
  setUp(() {
    initial = nutritionJson(full: true)..['liked_ingredients'] = ['old'];
    repo = FakeNutritionRepository(json: Map.of(initial));
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

  Future<void> visit(_Scenario s) async {
    await controller.load();
    while (controller.step < s.step) {
      expect(await controller.save(), NutritionSaveResult.advanced);
    }
    s.edit(controller);
  }

  Map<Object, Object?> draft() => {
    for (final f in NutritionField.values) f: controller.input(f),
    for (final f in PreferenceField.values) f: controller.preferenceInput(f),
    for (final f in PreferenceList.values) f: controller.ingredients(f),
  };
  void restoreInitialDraft() {
    final profile = NutritionProfile.fromJson(initial);
    for (final f in NutritionField.values) {
      controller.edit(f, profile.values[f] ?? '');
    }
    for (final f in PreferenceField.values) {
      controller.editPreference(f, profile.preferences.text(f));
    }
    for (final f in PreferenceList.values) {
      controller.editIngredients(f, profile.preferences.list(f));
    }
  }

  for (final s in scenarios) {
    for (final field in s.patch.keys) {
      test(
        '${s.name}: $field mismatch preserves the whole draft/baseline; explicit retry',
        () async {
          await visit(s);
          final before = draft();
          repo.saveHandler = (patch) async => NutritionProfile.fromJson({
            ...initial, ...patch.json, field: initial[field],
            // The decoder requires a valid pair even for a mismatching clear reply.
            if (s.name == 'clear practical' &&
                field != 'max_cooking_time_minutes') ...{
              'weekly_food_budget_amount': initial['weekly_food_budget_amount'],
              'budget_currency': initial['budget_currency'],
            },
          });
          expect(await controller.save(), NutritionSaveResult.rejected);
          expect(controller.failure?.type, NutritionFailureType.unexpected);
          expect(controller.step, s.step);
          expect(controller.saving, isFalse);
          expect(controller.lastSaveWrote, isNull);
          expect(draft(), before);
          expect(controller.dirty, isTrue);
          expect(repo.patches.single, s.patch);
          expect(repo.loads, 1);
          restoreInitialDraft();
          expect(
            controller.dirty,
            isFalse,
            reason: 'No part of the baseline may be acknowledged',
          );
          s.edit(controller);
          repo.saveHandler = null;
          expect(await controller.save(), NutritionSaveResult.advanced);
          expect(repo.patches, [s.patch, s.patch]);
          expect(repo.loads, 1);
          expect(controller.step, s.step + 1);
          expect(controller.lastSaveWrote, isTrue);
          expect(controller.dirty, isFalse);
          controller.back();
          expect(await controller.save(), NutritionSaveResult.advanced);
          expect(repo.patches, hasLength(2));
        },
      );
    }
  }

  for (final field in PreferenceList.values) {
    for (final returned in [
      <String>['rice', 'rice', 'beans'],
      <String>['rice', 'beans'],
    ]) {
      test('$field order and duplicates must match $returned', () async {
        final s = scenarios[3];
        await visit(s);
        final key = switch (field) {
          PreferenceList.allergies => 'allergies',
          PreferenceList.likes => 'liked_ingredients',
          PreferenceList.dislikes => 'disliked_ingredients',
        };
        repo.saveHandler = (patch) async => NutritionProfile.fromJson({
          ...initial,
          ...patch.json,
          key: returned,
        });
        final before = draft();
        expect(await controller.save(), NutritionSaveResult.rejected);
        expect(draft(), before);
        expect(repo.patches, hasLength(1));
      });
    }
  }

  for (final step in [1, 3, 4]) {
    test(
      'step $step accepts equivalent decimals and ignores unsent fields',
      () async {
        final s = scenarios.firstWhere((s) => s.step == step);
        await controller.load();
        while (controller.step < step) {
          await controller.save();
        }
        if (step == 1) {
          controller.edit(NutritionField.weight, '081,20');
        } else if (step == 3) {
          controller.editPreference(PreferenceField.diet, ' custom diet ');
        } else {
          controller.editPreference(PreferenceField.budgetAmount, '050,1');
        }
        repo.saveHandler = (patch) async => NutritionProfile.fromJson({
          ...initial,
          ...patch.json,
          if (step == 1) ...{'weight_kg': '81.2', 'height_cm': '190.0'},
          if (step == 3) 'liked_ingredients': ['another device'],
          if (step == 4) ...{
            'weekly_food_budget_amount': '50.10',
            'max_cooking_time_minutes': 90,
          },
        });
        expect(await controller.save(), NutritionSaveResult.advanced);
        expect(repo.patches.single, switch (step) {
          1 => {'weight_kg': '081.20'},
          3 => {'diet_type': 'custom diet'},
          _ => {'weekly_food_budget_amount': '050.1', 'budget_currency': 'EUR'},
        });
        expect(controller.step, s.step + 1);
        expect(controller.lastSaveWrote, isTrue);
        expect(controller.dirty, isFalse);
      },
    );
  }
  test('height equivalent decimal reply succeeds', () async {
    await controller.load();
    await controller.save();
    controller.edit(NutritionField.height, '181,0');
    repo.saveHandler = (patch) async => NutritionProfile.fromJson({
      ...initial,
      ...patch.json,
      'height_cm': '181',
    });
    expect(await controller.save(), NutritionSaveResult.advanced);
    expect(controller.dirty, isFalse);
  });

  for (final s in [scenarios[0], scenarios[3], scenarios[4]]) {
    for (final sameUser in [false, true]) {
      for (final matching in [false, true]) {
        test(
          '${s.name}: late matching=$matching after ${sameUser ? 'A→A' : 'A→B'} is stale',
          () async {
            await visit(s);
            final reply = Completer<NutritionProfile>();
            repo.saveHandler = (_) => reply.future;
            final pending = controller.save();
            await storage.writeTokenPair(
              AuthTokenPair(
                accessToken: sameUser ? 'synthetic-a' : 'synthetic-b',
                refreshToken: 'synthetic-new',
              ),
            );
            final next = NutritionSetupController(
              repository: repo,
              storage: storage,
              isAuthenticated: () => true,
            );
            addTearDown(next.dispose);
            await next.load();
            next.edit(NutritionField.goal, 'lose_weight');
            reply.complete(
              NutritionProfile.fromJson({...initial, if (matching) ...s.patch}),
            );
            expect(await pending, NutritionSaveResult.stale);
            expect(controller.failure, isNull);
            expect(controller.lastSaveWrote, isNull);
            expect(controller.loaded, isFalse);
            expect(next.input(NutritionField.goal), 'lose_weight');
            expect(next.step, 0);
            expect(next.failure, isNull);
            expect(repo.patches, [s.patch]);
            expect(repo.loads, 2);
          },
        );
      }
    }
  }
}

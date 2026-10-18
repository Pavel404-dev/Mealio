import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/presentation/nutrition_setup_controller.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  late FakeNutritionRepository repository;
  late FakeSecureStorageService storage;
  late NutritionSetupController controller;
  late bool authenticated;

  setUp(() {
    repository = FakeNutritionRepository();
    storage = FakeSecureStorageService(
      accessToken: 'synthetic-a',
      refreshToken: 'synthetic-refresh-a',
    );
    authenticated = true;
    controller = NutritionSetupController(
      repository: repository,
      storage: storage,
      isAuthenticated: () => authenticated,
    );
  });
  tearDown(() => controller.dispose());

  void fillBody() {
    controller.edit(NutritionField.sex, 'female');
    controller.edit(NutritionField.birthDate, '2000-02-29');
    controller.edit(NutritionField.height, '193,0');
    controller.edit(NutritionField.weight, '78,40');
  }

  test(
    'opening GET and default maintain never write or mark completion',
    () async {
      await controller.load();
      expect(controller.step, 0);
      expect(controller.input(NutritionField.goal), 'maintain');
      expect(controller.input(NutritionField.height), isEmpty);
      expect(controller.dirty, isFalse);
      expect(repository.loads, 1);
      expect(repository.saves, isEmpty);
      expect(await controller.save(), NutritionSaveResult.advanced);
      expect(controller.step, 1);
      expect(repository.saves, isEmpty);
      expect(controller.lastSaveWrote, isFalse);
    },
  );

  test(
    'partial profile requires all body inputs without invented values',
    () async {
      repository.json['height_cm'] = '170.0';
      await controller.load();
      await controller.save();
      expect(controller.input(NutritionField.height), '170.0');
      expect(await controller.save(), NutritionSaveResult.rejected);
      for (final field in [
        NutritionField.sex,
        NutritionField.birthDate,
        NutritionField.weight,
      ]) {
        expect(controller.error(field), NutritionInputError.required);
      }
      expect(controller.error(NutritionField.height), isNull);
      expect(controller.step, 1);
      expect(repository.saves, isEmpty);
    },
  );

  test(
    'saves each step with exact changed subset and validates empty activity',
    () async {
      await controller.load();
      controller.edit(NutritionField.goal, 'lose_weight');
      await controller.save();
      expect(repository.saves.single, {NutritionField.goal: 'lose_weight'});
      fillBody();
      await controller.save();
      expect(repository.saves.last, {
        NutritionField.sex: 'female',
        NutritionField.birthDate: '2000-02-29',
        NutritionField.height: '193.0',
        NutritionField.weight: '78.40',
      });
      expect(await controller.save(), NutritionSaveResult.rejected);
      expect(
        controller.error(NutritionField.activity),
        NutritionInputError.required,
      );
      controller.edit(NutritionField.activity, 'very_active');
      expect(await controller.save(), NutritionSaveResult.finished);
      expect(repository.saves.last, {NutritionField.activity: 'very_active'});
      expect(repository.json['daily_calories_target'], 2400);
      expect(repository.json['allergies'], ['synthetic-allergen']);
      expect(controller.dirty, isFalse);
    },
  );

  test(
    'weight-only edit on full profile preserves other values and nullable omissions',
    () async {
      repository.json.addAll(nutritionJson(full: true));
      await controller.load();
      await controller.save();
      controller.edit(NutritionField.weight, '78,40');
      await controller.save();
      expect(repository.saves.single, {NutritionField.weight: '78.40'});
    },
  );

  test(
    'Back and another step save response preserve dirty body and activity',
    () async {
      repository.json.addAll(nutritionJson(full: true));
      await controller.load();
      await controller.save();
      controller.edit(NutritionField.height, '193,0');
      controller.back();
      controller.edit(NutritionField.goal, 'gain_weight');
      await controller.save();
      expect(controller.input(NutritionField.height), '193,0');
      expect(controller.dirty, isTrue);
      await controller.save();
      controller.edit(NutritionField.activity, 'extra_active');
      controller.back();
      controller.edit(NutritionField.weight, '78,40');
      await controller.save();
      expect(controller.input(NutritionField.activity), 'extra_active');
      expect(controller.dirty, isTrue);
      expect(repository.loads, 1);
    },
  );

  test(
    'no duplicate save, edits, Back or advance before confirmed response',
    () async {
      await controller.load();
      controller.edit(NutritionField.goal, 'gain_weight');
      final pending = Completer<NutritionProfile>();
      repository.saveHandler = (_) => pending.future;
      final save = controller.save();
      expect(controller.saving, isTrue);
      expect(controller.step, 0);
      expect(await controller.save(), NutritionSaveResult.rejected);
      controller.edit(NutritionField.goal, 'lose_weight');
      controller.back();
      expect(controller.input(NutritionField.goal), 'gain_weight');
      expect(repository.saves, hasLength(1));
      pending.complete(
        NutritionProfile.fromJson(nutritionJson()..['goal'] = 'gain_weight'),
      );
      expect(await save, NutritionSaveResult.advanced);
      expect(controller.step, 1);
    },
  );

  test(
    'load failure and retry, duplicate loads, no later GET clobber',
    () async {
      final pending = Completer<NutritionProfile>();
      repository.loadHandler = () => pending.future;
      final load = controller.load();
      await controller.load();
      expect(repository.loads, 1);
      pending.completeError(
        const NutritionFailure(NutritionFailureType.connection),
      );
      await load;
      expect(controller.loaded, isFalse);
      expect(controller.failure?.type, NutritionFailureType.connection);
      repository.loadHandler = null;
      await controller.load();
      controller.edit(NutritionField.goal, 'gain_weight');
      await controller.load();
      expect(repository.loads, 2);
      expect(controller.input(NutritionField.goal), 'gain_weight');
    },
  );

  test(
    'ambiguous failed save retains input; explicit retry sends same exact subset',
    () async {
      await controller.load();
      await controller.save();
      fillBody();
      repository.saveHandler = (_) =>
          Future.error(const NutritionFailure(NutritionFailureType.connection));
      expect(await controller.save(), NutritionSaveResult.rejected);
      expect(controller.step, 1);
      expect(controller.input(NutritionField.weight), '78,40');
      expect(controller.dirty, isTrue);
      expect(repository.saves, hasLength(1));
      repository.saveHandler = null;
      expect(await controller.save(), NutritionSaveResult.advanced);
      expect(repository.saves, hasLength(2));
      expect(repository.saves.first, repository.saves.last);
    },
  );

  test(
    'new route/controller starts at step 1 with saved values only',
    () async {
      await controller.load();
      controller.edit(NutritionField.goal, 'gain_weight');
      await controller.save();
      fillBody();
      await controller.save();
      controller.edit(NutritionField.activity, 'extra_active');
      final reopened = NutritionSetupController(
        repository: repository,
        storage: storage,
        isAuthenticated: () => true,
      );
      addTearDown(reopened.dispose);
      await reopened.load();
      expect(reopened.step, 0);
      expect(reopened.input(NutritionField.goal), 'gain_weight');
      expect(reopened.input(NutritionField.weight), '78.40');
      expect(reopened.input(NutritionField.activity), isEmpty);
    },
  );

  for (final save in [false, true]) {
    for (final failure in [false, true]) {
      for (final sameUser in [false, true]) {
        test(
          'late ${save ? 'PATCH' : 'GET'} ${failure ? 'failure' : 'success'} after ${sameUser ? 'A→A' : 'A→B'} preserves newer draft',
          () async {
            final pending = Completer<NutritionProfile>();
            final Future<Object?> operation;
            if (save) {
              await controller.load();
              controller.edit(NutritionField.goal, 'gain_weight');
              repository.saveHandler = (_) => pending.future;
              operation = controller.save();
            } else {
              repository.loadHandler = () => pending.future;
              operation = controller.load();
            }
            // Even identical tokens/new login A must invalidate the first owner.
            authenticated = false;
            await storage.deleteTokenPair();
            controller.checkOwnership();
            expect(controller.input(NutritionField.goal), isEmpty);
            expect(controller.loaded, isFalse);
            await storage.writeTokenPair(
              AuthTokenPair(
                accessToken: sameUser ? 'synthetic-a' : 'synthetic-b',
                refreshToken: sameUser
                    ? 'synthetic-refresh-a'
                    : 'synthetic-refresh-b',
              ),
            );
            authenticated = true;
            final nextRepository = FakeNutritionRepository(
              json: nutritionJson(full: true),
            );
            final next = NutritionSetupController(
              repository: nextRepository,
              storage: storage,
              isAuthenticated: () => authenticated,
            );
            addTearDown(next.dispose);
            await next.load();
            next.edit(NutritionField.goal, 'lose_weight');
            if (failure) {
              pending.completeError(
                const NutritionFailure(NutritionFailureType.connection),
              );
            } else {
              pending.complete(
                NutritionProfile.fromJson(
                  nutritionJson()..['goal'] = 'gain_weight',
                ),
              );
            }
            await operation;
            expect(next.input(NutritionField.goal), 'lose_weight');
            expect(next.step, 0);
            expect(next.failure, isNull);
            expect(controller.input(NutritionField.goal), isEmpty);
            expect(controller.failure, isNull);
            await controller.load();
            expect(await controller.save(), NutritionSaveResult.stale);
            expect(nextRepository.saves, isEmpty);
          },
        );
      }
    }
  }

  test(
    'lifetime changes without auth notification are checked before retry/dispatch',
    () async {
      repository.loadHandler = () =>
          Future.error(const NutritionFailure(NutritionFailureType.connection));
      await controller.load();
      final delayedRetry = Completer<void>();
      final scheduledRetry = delayedRetry.future.then((_) => controller.load());
      await storage.deleteTokenPair();
      delayedRetry.complete();
      await scheduledRetry;
      expect(repository.loads, 1);
      expect(controller.failure, isNull);
      expect(controller.isCurrent, isFalse);
    },
  );

  test(
    'same lifetime refresh preserves dirty values and submitted errors',
    () async {
      await controller.load();
      await controller.save();
      controller.edit(NutritionField.weight, '78,400');
      await controller.save();
      final lifetime = storage.sessionLifetime;
      expect(
        await storage.replaceTokenPairIfRefreshTokenMatches(
          expectedRefreshToken: 'synthetic-refresh-a',
          pair: const AuthTokenPair(
            accessToken: 'synthetic-rotated',
            refreshToken: 'synthetic-rotated-refresh',
          ),
        ),
        isTrue,
      );
      expect(storage.sessionLifetime, lifetime);
      expect(controller.checkOwnership(), isTrue);
      expect(controller.input(NutritionField.weight), '78,400');
      expect(
        controller.error(NutritionField.weight),
        NutritionInputError.weight,
      );
      expect(controller.step, 1);
    },
  );

  for (final save in [false, true]) {
    for (final fails in [false, true]) {
      test(
        'disposed ${save ? 'save' : 'load'} ignores late ${fails ? 'failure' : 'success'}',
        () async {
          final separate = NutritionSetupController(
            repository: repository,
            storage: storage,
            isAuthenticated: () => true,
          );
          final pending = Completer<NutritionProfile>();
          final Future<Object?> operation;
          if (save) {
            await separate.load();
            separate.edit(NutritionField.goal, 'gain_weight');
            repository.saveHandler = (_) => pending.future;
            operation = separate.save();
          } else {
            repository.loadHandler = () => pending.future;
            operation = separate.load();
          }
          separate.dispose();
          if (fails) {
            pending.completeError(StateError('synthetic'));
          } else {
            pending.complete(NutritionProfile.fromJson(nutritionJson()));
          }
          await operation;
          expect(separate.loaded, isFalse);
          expect(separate.input(NutritionField.goal), isEmpty);
        },
      );
    }
  }
}

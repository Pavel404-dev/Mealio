import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/features/recipes/domain/recipe_detail.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';
import 'package:mealio/features/recipes/presentation/recipe_detail_controller.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

void main() {
  late FakeSecureStorageService storage;
  late FakeRecipeRepository repository;
  late RecipeDetailController controller;
  late bool authenticated;

  setUp(() {
    storage = FakeSecureStorageService(
      accessToken: 'test-access-A',
      refreshToken: 'test-refresh-A',
    );
    repository = FakeRecipeRepository();
    authenticated = true;
    controller = RecipeDetailController(
      recipeId: 'recipe-1',
      repository: repository,
      storage: storage,
      isAuthenticated: () => authenticated,
    );
    addTearDown(controller.dispose);
  });

  test(
    'one pending request owns the ID/lifetime/cancellation and blocks double loading',
    () async {
      final response = Completer<RecipeDetail>();
      repository.detailHandler = (_) => response.future;
      final pending = controller.load();
      expect(controller.loading, isTrue);
      expect(controller.detail, isNull);
      await controller.load();
      expect(repository.detailCalls, hasLength(1));
      final request = repository.detailCalls.single;
      expect(request.recipeId, 'recipe-1');
      expect(request.lifetime, 0);
      expect(request.cancelToken?.isCancelled, isFalse);
      response.complete(recipeDetailFixture());
      await pending;
      expect(controller.detail?.recipe.servings, 4);
      expect(controller.detail?.recipe.totalCalories, 330);
      expect(controller.loading, isFalse);
      expect(controller.failure, isNull);
      await controller.load();
      expect(repository.detailCalls, hasLength(1));
    },
  );

  for (final failure in RecipeFailureType.values) {
    test(
      '$failure stays a safe error, explicit retry starts a fresh attempt',
      () async {
        repository.detailHandler = (_) => throw RecipeFailure(failure);
        await controller.load();
        expect(controller.failure?.type, failure);
        expect(controller.detail, isNull);
        expect(controller.loading, isFalse);
        final firstToken = repository.detailCalls.single.cancelToken;
        repository.detailHandler = (_) =>
            recipeDetailFixture(title: 'Fresh detail');
        await controller.load();
        expect(repository.detailCalls, hasLength(2));
        expect(
          repository.detailCalls.last.cancelToken,
          isNot(same(firstToken)),
        );
        expect(controller.detail?.recipe.title, 'Fresh detail');
        expect(controller.failure, isNull);
      },
    );
  }

  test('unknown exception is not exposed', () async {
    repository.detailHandler = (_) =>
        throw StateError('synthetic-private-detail');
    await controller.load();
    expect(controller.failure?.type, RecipeFailureType.unexpected);
    expect(controller.detail, isNull);
  });

  test('current auth notifications/rotation keep loaded detail', () async {
    await controller.load();
    final first = controller.detail;
    final rotated = await storage.replaceTokenPairIfRefreshTokenMatches(
      expectedRefreshToken: 'test-refresh-A',
      pair: const AuthTokenPair(
        accessToken: 'test-rotated',
        refreshToken: 'test-rotated-refresh',
      ),
    );
    expect(rotated, isTrue);
    expect(controller.checkOwnership(), isTrue);
    await controller.load();
    expect(controller.detail, same(first));
    expect(repository.detailCalls, hasLength(1));
  });

  test('auth loss clears idle detail and old visit cannot revive', () async {
    await controller.load();
    authenticated = false;
    expect(controller.checkOwnership(), isFalse);
    expect(controller.detail, isNull);
    authenticated = true;
    await controller.load();
    expect(controller.isCurrent, isFalse);
    expect(repository.detailCalls, hasLength(1));
  });

  for (final lateError in [false, true]) {
    test(
      'relogin cancels pending work and ignores late ${lateError ? 'error' : 'success'}',
      () async {
        final response = Completer<RecipeDetail>();
        repository.detailHandler = (_) => response.future;
        final pending = controller.load();
        await storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'test-new',
            refreshToken: 'test-new-refresh',
          ),
        );
        expect(controller.checkOwnership(), isFalse);
        expect(repository.detailCalls.single.cancelToken?.isCancelled, isTrue);
        if (lateError) {
          response.completeError(
            const RecipeFailure(RecipeFailureType.authentication),
          );
        } else {
          response.complete(recipeDetailFixture(title: 'Old session'));
        }
        await pending;
        expect(controller.detail, isNull);
        expect(controller.failure, isNull);
        expect(controller.loading, isFalse);
        expect(storage.accessToken, 'test-new');
        await controller.load();
        expect(repository.detailCalls, hasLength(1));
      },
    );
  }

  test(
    'disposal cancels pending work and ignores completion without notifications',
    () async {
      final local = RecipeDetailController(
        recipeId: 'other-id',
        repository: repository,
        storage: storage,
        isAuthenticated: () => true,
      );
      final response = Completer<RecipeDetail>();
      repository.detailHandler = (_) => response.future;
      final pending = local.load();
      local.dispose();
      expect(repository.detailCalls.single.cancelToken?.isCancelled, isTrue);
      response.complete(recipeDetailFixture(id: 'other-id'));
      await pending;
      expect(local.detail, isNull);
      await local.load();
      expect(repository.detailCalls, hasLength(1));
    },
  );

  test('no request when unauthenticated', () async {
    authenticated = false;
    await controller.load();
    expect(repository.detailCalls, isEmpty);
  });
}

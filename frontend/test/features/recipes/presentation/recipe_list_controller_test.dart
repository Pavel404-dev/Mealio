import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';
import 'package:mealio/features/recipes/presentation/recipe_list_controller.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

void main() {
  late FakeSecureStorageService storage;
  late FakeRecipeRepository repository;
  late RecipeListController controller;
  late bool authenticated;

  setUp(() {
    storage = FakeSecureStorageService(
      accessToken: 'test-access-A',
      refreshToken: 'test-refresh-A',
    );
    repository = FakeRecipeRepository();
    authenticated = true;
    controller = RecipeListController(
      repository: repository,
      storage: storage,
      isAuthenticated: () => authenticated,
    );
    addTearDown(controller.dispose);
  });

  test(
    'loads once, blocks duplicate pending loads, keeps an immutable page',
    () async {
      final response = Completer<List<Recipe>>();
      repository.handler = (_) => response.future;
      final pending = controller.load();
      expect(controller.loading, isTrue);
      expect(controller.loaded, isFalse);
      await controller.load();
      await controller.retry();
      await controller.loadMore();
      expect(repository.calls, [(lifetime: 0, limit: 50, offset: 0)]);
      response.complete(recipePage(count: 1));
      await pending;
      expect(controller.loading, isFalse);
      expect(controller.loaded, isTrue);
      expect(controller.items.single.id, 'recipe-0');
      expect(controller.hasMore, isFalse);
      expect(controller.failure, isNull);
      expect(() => controller.items.clear(), throwsUnsupportedError);
      await controller.load();
      await controller.loadMore();
      expect(repository.calls, hasLength(1));
    },
  );

  test('empty initial page is success and has no pagination', () async {
    await controller.load();
    expect(controller.loaded, isTrue);
    expect(controller.items, isEmpty);
    expect(controller.hasMore, isFalse);
    expect(controller.failure, isNull);
    await controller.loadMore();
    expect(repository.calls, hasLength(1));
  });

  test(
    'initial error has no automatic retry; explicit retry loads offset zero',
    () async {
      repository.handler = (_) =>
          throw const RecipeFailure(RecipeFailureType.connection);
      await controller.load();
      expect(controller.loaded, isFalse);
      expect(controller.loading, isFalse);
      expect(controller.items, isEmpty);
      expect(controller.failure?.type, RecipeFailureType.connection);
      await Future<void>.delayed(const Duration(milliseconds: 500));
      expect(repository.calls, hasLength(1));
      repository.handler = (_) => recipePage(count: 1);
      await controller.retry();
      expect(repository.calls.map((call) => call.offset), [0, 0]);
      expect(controller.items, hasLength(1));
      expect(controller.failure, isNull);
    },
  );

  test(
    'page failure preserves data/offset and duplicate retry does not append twice',
    () async {
      repository.handler = (_) => recipePage();
      await controller.load();
      repository.handler = (_) =>
          throw const RecipeFailure(RecipeFailureType.rateLimited);
      await controller.loadMore();
      expect(controller.items, hasLength(50));
      expect(controller.hasMore, isTrue);
      expect(controller.failure?.type, RecipeFailureType.rateLimited);
      final response = Completer<List<Recipe>>();
      repository.handler = (_) => response.future;
      final retry = controller.retry();
      expect(controller.failure, isNull);
      expect(controller.loading, isTrue);
      expect(controller.items, hasLength(50));
      await controller.retry();
      await controller.loadMore();
      response.complete(recipePage(start: 50, count: 1));
      await retry;
      expect(repository.calls.map((call) => call.offset), [0, 50, 50]);
      expect(controller.items, hasLength(51));
      expect(controller.items.last.id, 'recipe-50');
      expect(controller.hasMore, isFalse);
    },
  );

  test(
    'deduplicates overlap but advances by server row count, not unique items',
    () async {
      repository.handler = (_) => recipePage();
      await controller.load();
      repository.handler = (_) => recipePage(start: 49);
      await controller.loadMore();
      expect(controller.items, hasLength(99));
      expect(controller.items.map((item) => item.id).toSet(), hasLength(99));
      repository.handler = (_) => recipePage(start: 99, count: 1);
      await controller.loadMore();
      expect(repository.calls.map((call) => call.offset), [0, 50, 100]);
      expect(controller.items, hasLength(100));
      expect(controller.items.last.id, 'recipe-99');
      expect(controller.hasMore, isFalse);
    },
  );

  test('exactly full final page ends on the following empty page', () async {
    repository.handler = (_) => recipePage();
    await controller.load();
    expect(controller.hasMore, isTrue);
    repository.handler = (_) => [];
    await controller.loadMore();
    expect(controller.items, hasLength(50));
    expect(controller.hasMore, isFalse);
    await controller.loadMore();
    expect(repository.calls.map((call) => call.offset), [0, 50]);
  });

  test('unknown failures are mapped safely and remain retryable', () async {
    repository.handler = (_) => throw StateError('synthetic-private-detail');
    await controller.load();
    expect(controller.failure?.type, RecipeFailureType.unexpected);
    repository.handler = (_) => [];
    await controller.retry();
    expect(controller.loaded, isTrue);
  });

  test(
    'auth transition clears idle cached rows and permanently retires the visit',
    () async {
      repository.handler = (_) => recipePage();
      await controller.load();
      authenticated = false;
      expect(controller.checkOwnership(), isFalse);
      expect(controller.items, isEmpty);
      expect(controller.loaded, isFalse);
      authenticated = true;
      await controller.load();
      await controller.retry();
      expect(controller.isCurrent, isFalse);
      expect(repository.calls, hasLength(1));
    },
  );

  test(
    'same lifetime notifications and token rotation preserve loaded pages',
    () async {
      repository.handler = (_) => recipePage();
      await controller.load();
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
      expect(controller.items, hasLength(50));
      expect(repository.calls, hasLength(1));
    },
  );

  for (final lateError in [false, true]) {
    for (final initial in [false, true]) {
      test(
        'relogin rejects old ${initial ? 'initial' : 'next'} page ${lateError ? 'error' : 'success'}',
        () async {
          if (!initial) {
            repository.handler = (_) => recipePage();
            await controller.load();
          }
          final response = Completer<List<Recipe>>();
          repository.handler = (_) => response.future;
          final pending = initial ? controller.load() : controller.loadMore();
          await storage.writeTokenPair(
            const AuthTokenPair(
              accessToken: 'test-new',
              refreshToken: 'test-new-refresh',
            ),
          );
          if (lateError) {
            response.completeError(
              const RecipeFailure(RecipeFailureType.authentication),
            );
          } else {
            response.complete(recipePage(start: 50, count: 1));
          }
          await pending;
          expect(controller.isCurrent, isFalse);
          expect(controller.items, isEmpty);
          expect(controller.failure, isNull);
          expect(controller.loading, isFalse);
          final calls = repository.calls.length;
          await controller.retry();
          expect(repository.calls, hasLength(calls));
        },
      );
    }
  }

  test('no request while unauthenticated', () async {
    authenticated = false;
    await controller.load();
    expect(repository.calls, isEmpty);
  });

  test(
    'disposed visit ignores pending completion and sends no more requests',
    () async {
      final response = Completer<List<Recipe>>();
      final local = RecipeListController(
        repository: repository,
        storage: storage,
        isAuthenticated: () => true,
      );
      repository.handler = (_) => response.future;
      final pending = local.load();
      local.dispose();
      response.complete(recipePage(count: 1));
      await pending;
      expect(local.items, isEmpty);
      await local.retry();
      expect(repository.calls, hasLength(1));
    },
  );
}

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/session_request.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/recipes/data/recipe_repository.dart';
import 'package:mealio/features/recipes/domain/recipe_detail.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

Map<String, dynamic> composedRecipe(int count) =>
    recipeJson()
      ..['recipe_ingredients'] = [
        for (var i = 0; i < count; i++)
          <String, dynamic>{
            'id': 'composition-$i',
            'recipe_id': 'recipe-1',
            'ingredient_id': 'ingredient-$i',
            'quantity_g': '${i + 1}.25',
          },
      ];

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;
  late RecipeRepository repository;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();
    repository = RecipeRepository(
      apiClient: ApiClient(createFakeDio(adapter), storage: storage),
      storage: storage,
    );
  });

  Future<RecipeDetail> load({
    String id = 'recipe-1',
    int? lifetime,
    CancelToken? cancelToken,
  }) => repository.getRecipeDetail(
    recipeId: id,
    lifetime: lifetime ?? storage.sessionLifetime,
    cancelToken: cancelToken,
  );

  Matcher failure(RecipeFailureType type) =>
      isA<RecipeFailure>().having((e) => e.type, 'type', type);

  test(
    'fresh detail and exact catalog UUIDs preserve whole-recipe data and order',
    () async {
      final json = composedRecipe(2);
      // An overlapping UUID in a read response is resolved once, not per row.
      (json['recipe_ingredients'] as List).add({
        'id': 'composition-repeat',
        'recipe_id': 'recipe-1',
        'ingredient_id': 'ingredient-0',
        'quantity_g': '99.99',
      });
      adapter.responseHandler = (request) => FakeHttpResponse(
        statusCode: 200,
        body: request.path == '/recipes/recipe-1'
            ? json
            : recipeIngredientJson(
                id: request.path.split('/').last,
                name: 'Имя {server}',
              ),
      );
      final detail = await load();
      expect(detail.recipe.servings, 4);
      expect(detail.recipe.totalCalories, 330);
      expect(detail.recipe.totalCarbsG, 0);
      expect(detail.recipe.instructions, 'First step.\nSecond step.');
      expect(detail.recipe.ingredients.map((e) => e.ingredientId), [
        'ingredient-0',
        'ingredient-1',
        'ingredient-0',
      ]);
      expect(detail.recipe.ingredients.map((e) => e.quantityG), [
        1.25,
        2.25,
        99.99,
      ]);
      expect(detail.ingredientNames, {
        'ingredient-0': 'Имя {server}',
        'ingredient-1': 'Имя {server}',
      });
      expect(() => detail.ingredientNames.clear(), throwsUnsupportedError);
      expect(adapter.requests.map((e) => e.path), [
        '/recipes/recipe-1',
        '/ingredients/ingredient-0',
        '/ingredients/ingredient-1',
      ]);
      for (final request in adapter.requests) {
        expect(request.method, 'GET');
        expect(request.data, isNull);
        expect(request.queryParameters, isEmpty);
        expect(request.extra[sessionLifetimeKey], 0);
      }
    },
  );

  test(
    'empty composition needs no catalog but retains instructions and null totals',
    () async {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: 200,
          body: composedRecipe(0)..['total_protein_g'] = null,
        ),
      );
      final detail = await load();
      expect(detail.recipe.ingredients, isEmpty);
      expect(detail.ingredientNames, isEmpty);
      expect(detail.recipe.instructions, isNotEmpty);
      expect(detail.recipe.totalProteinG, isNull);
      expect(adapter.requests, hasLength(1));
    },
  );

  test(
    'encodes path IDs rather than interpreting slash, query or fragment',
    () async {
      const id = 'recipe/with?query#fragment';
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: 200,
          body: recipeJson(id: id)..['recipe_ingredients'] = [],
        ),
      );
      expect((await load(id: id)).recipe.id, id);
      expect(
        adapter.requests.single.path,
        '/recipes/${Uri.encodeComponent(id)}',
      );
      expect(adapter.requests.single.queryParameters, isEmpty);
    },
  );

  test(
    'catalog dispatch is bounded to four and subsequent batches keep the lifetime',
    () async {
      final started = Completer<void>();
      final release = Completer<void>();
      var active = 0;
      var maximum = 0;
      adapter.responseHandler = (request) async {
        if (request.path.startsWith('/recipes/')) {
          return FakeHttpResponse(statusCode: 200, body: composedRecipe(7));
        }
        active++;
        if (active > maximum) maximum = active;
        if (active == 4 && !started.isCompleted) started.complete();
        await release.future;
        active--;
        return FakeHttpResponse(
          statusCode: 200,
          body: recipeIngredientJson(id: request.path.split('/').last),
        );
      };
      final pending = load();
      await started.future;
      expect(adapter.requests, hasLength(5));
      release.complete();
      final detail = await pending;
      expect(maximum, 4);
      expect(detail.ingredientNames, hasLength(7));
      expect(adapter.requests, hasLength(8));
      expect(adapter.requests.map((e) => e.extra[sessionLifetimeKey]).toSet(), {
        0,
      });
    },
  );

  for (final catalog in [false, true]) {
    for (final status in [201, 401, 404, 422, 429, 500]) {
      test(
        '${catalog ? 'catalog' : 'recipe'} status $status is safe and scoped',
        () async {
          adapter.responseHandler = (request) {
            if (catalog && request.path.startsWith('/recipes/')) {
              return FakeHttpResponse(statusCode: 200, body: recipeJson());
            }
            return FakeHttpResponse(
              statusCode: status,
              body: {'detail': 'synthetic-private-detail'},
            );
          };
          final expected = switch (status) {
            401 => RecipeFailureType.authentication,
            404 =>
              catalog
                  ? RecipeFailureType.ingredientUnavailable
                  : RecipeFailureType.unavailable,
            429 => RecipeFailureType.rateLimited,
            _ => RecipeFailureType.unexpected,
          };
          await expectLater(load(), throwsA(failure(expected)));
          expect(adapter.requests, hasLength(catalog ? 2 : 1));
        },
      );
    }
    test(
      '${catalog ? 'catalog' : 'recipe'} connection failure is retryable',
      () async {
        adapter.responseHandler = (request) {
          if (catalog && request.path.startsWith('/recipes/')) {
            return FakeHttpResponse(statusCode: 200, body: recipeJson());
          }
          return const FakeHttpResponse.error(DioExceptionType.connectionError);
        };
        await expectLater(
          load(),
          throwsA(failure(RecipeFailureType.connection)),
        );
      },
    );
    for (final malformed in [
      null,
      [],
      {'id': 'invalid'},
    ]) {
      test(
        '${catalog ? 'catalog' : 'recipe'} malformed response $malformed is not published',
        () async {
          adapter.responseHandler = (request) => FakeHttpResponse(
            statusCode: 200,
            body: catalog && request.path.startsWith('/recipes/')
                ? recipeJson()
                : malformed,
          );
          await expectLater(
            load(),
            throwsA(failure(RecipeFailureType.unexpected)),
          );
        },
      );
    }
  }

  test(
    'recipe/ingredient identity mismatches are rejected before publication',
    () async {
      for (final stage in ['recipe', 'composition', 'ingredient']) {
        final json = recipeJson();
        if (stage == 'recipe') json['id'] = 'other-recipe';
        if (stage == 'composition') {
          (json['recipe_ingredients'] as List).single['recipe_id'] =
              'other-recipe';
        }
        adapter.responseHandler = (request) => FakeHttpResponse(
          statusCode: 200,
          body: request.path.startsWith('/recipes/')
              ? json
              : recipeIngredientJson(id: 'wrong-ingredient'),
        );
        final before = adapter.requests.length;
        await expectLater(
          load(),
          throwsA(failure(RecipeFailureType.unexpected)),
        );
        expect(adapter.requests.length - before, stage == 'ingredient' ? 2 : 1);
      }
    },
  );

  test(
    'failed batch stops later lookups; retry rereads recipe and names',
    () async {
      var failed = true;
      adapter.responseHandler = (request) {
        if (request.path.startsWith('/recipes/')) {
          return FakeHttpResponse(
            statusCode: 200,
            body: composedRecipe(7)
              ..['title'] = failed ? 'Old title' : 'New title',
          );
        }
        return FakeHttpResponse(
          statusCode: failed ? 500 : 200,
          body: failed
              ? {}
              : recipeIngredientJson(id: request.path.split('/').last),
        );
      };
      await expectLater(load(), throwsA(failure(RecipeFailureType.unexpected)));
      expect(adapter.requests, hasLength(5));
      failed = false;
      final detail = await load();
      expect(detail.recipe.title, 'New title');
      expect(adapter.requests, hasLength(13));
      expect(
        adapter.requests.where((e) => e.path.startsWith('/recipes/')),
        hasLength(2),
      );
    },
  );

  test('DTO rejects a missing/blank name instead of guessing from an ID', () {
    for (final names in [
      <String, String>{},
      {'ingredient-1': '  '},
    ]) {
      expect(
        () => RecipeDetail(
          recipe: recipeDetailFixture().recipe,
          ingredientNames: names,
        ),
        throwsFormatException,
      );
    }
  });

  for (final duringCatalog in [false, true]) {
    for (final cancellation in [false, true]) {
      test(
        '${cancellation ? 'cancel' : 'relogin'} during ${duringCatalog ? 'catalog' : 'recipe'} stops subsequent work',
        () async {
          final started = Completer<void>();
          final release = Completer<void>();
          final cancelToken = CancelToken();
          var catalogCalls = 0;
          adapter.responseHandler = (request) async {
            final isRecipe = request.path.startsWith('/recipes/');
            if (isRecipe && duringCatalog) {
              return FakeHttpResponse(statusCode: 200, body: composedRecipe(7));
            }
            if (!isRecipe) catalogCalls++;
            if ((!duringCatalog || catalogCalls == 4) && !started.isCompleted) {
              started.complete();
            }
            await release.future;
            return FakeHttpResponse(
              statusCode: 200,
              body: isRecipe
                  ? composedRecipe(7)
                  : recipeIngredientJson(id: request.path.split('/').last),
            );
          };
          final result = expectLater(
            load(cancelToken: cancelToken),
            throwsA(
              cancellation
                  ? isA<DioException>().having(
                      (e) => e.type,
                      'type',
                      DioExceptionType.cancel,
                    )
                  : isA<SessionSuperseded>(),
            ),
          );
          await started.future;
          if (cancellation) {
            cancelToken.cancel();
          } else {
            await storage.writeTokenPair(
              const AuthTokenPair(
                accessToken: 'test-access-B',
                refreshToken: 'test-refresh-B',
              ),
            );
          }
          release.complete();
          await result;
          expect(adapter.requests, hasLength(duringCatalog ? 5 : 1));
          if (!cancellation) expect(storage.accessToken, 'test-access-B');
        },
      );
    }
  }

  test('pre-cancelled or stale request never dispatches', () async {
    final token = CancelToken()..cancel();
    await expectLater(load(cancelToken: token), throwsA(isA<DioException>()));
    final lifetime = storage.sessionLifetime;
    await storage.deleteTokenPair();
    await expectLater(
      load(lifetime: lifetime),
      throwsA(isA<SessionSuperseded>()),
    );
    expect(adapter.requests, isEmpty);
  });
}

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/session_request.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/recipes/data/recipe_repository.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

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

  Future<List<Recipe>> load({int? lifetime, int offset = 0}) =>
      repository.getRecipes(
        lifetime: lifetime ?? storage.sessionLifetime,
        limit: 50,
        offset: offset,
      );

  test(
    'GETs one explicit page with its lifetime, no catalog or write requests',
    () async {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: 200,
          body: [
            recipeJson(id: 'second'),
            recipeJson(id: 'first'),
          ],
        ),
      );
      final items = await load(offset: 50);
      expect(items.map((recipe) => recipe.id), ['second', 'first']);
      expect(items.first.servings, 4);
      expect(items.first.totalCalories, 330);
      expect(items.first.ingredients.single.quantityG, 200);
      expect(adapter.requests, hasLength(1));
      final request = adapter.requests.single;
      expect(request.method, 'GET');
      expect(request.path, '/recipes');
      expect(request.uri.path, '/api/v1/recipes');
      expect(request.queryParameters, {'limit': 50, 'offset': 50});
      expect(request.extra[sessionLifetimeKey], storage.sessionLifetime);
      expect(request.data, isNull);
      expect(() => items.clear(), throwsUnsupportedError);
    },
  );

  test('accepts an empty list as success', () async {
    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: []));
    expect(await load(), isEmpty);
  });

  for (final status in [201, 204, 401, 403, 422, 429, 500, 503]) {
    test('maps status $status without exposing server text', () async {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: status,
          body: {'detail': 'synthetic-private-detail'},
        ),
      );
      final expected = switch (status) {
        401 => RecipeFailureType.authentication,
        429 => RecipeFailureType.rateLimited,
        _ => RecipeFailureType.unexpected,
      };
      await expectLater(
        load(),
        throwsA(isA<RecipeFailure>().having((e) => e.type, 'type', expected)),
      );
      expect(adapter.requests, hasLength(1));
    });
  }
  for (final type in DioExceptionType.values) {
    test('safely maps transport $type', () async {
      adapter.enqueue(FakeHttpResponse.error(type));
      final expected = switch (type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.sendTimeout ||
        DioExceptionType.receiveTimeout ||
        DioExceptionType.transformTimeout ||
        DioExceptionType.connectionError => RecipeFailureType.connection,
        _ => RecipeFailureType.unexpected,
      };
      await expectLater(
        load(),
        throwsA(isA<RecipeFailure>().having((e) => e.type, 'type', expected)),
      );
    });
  }
  for (final body in [
    null,
    {},
    {'items': []},
    [null],
    [
      recipeJson(),
      {'id': 'broken'},
    ],
  ]) {
    test('rejects malformed 200 response $body', () async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: body));
      await expectLater(
        load(),
        throwsA(
          isA<RecipeFailure>().having(
            (e) => e.type,
            'type',
            RecipeFailureType.unexpected,
          ),
        ),
      );
    });
  }

  test('does not dispatch for an expired lifetime', () async {
    final lifetime = storage.sessionLifetime;
    await storage.deleteTokenPair();
    await expectLater(
      load(lifetime: lifetime),
      throwsA(isA<SessionSuperseded>()),
    );
    expect(adapter.requests, isEmpty);
  });

  for (final lateError in [false, true]) {
    test(
      'rejects stale ${lateError ? 'error' : 'success'} after a new login',
      () async {
        final response = Completer<FakeHttpResponse>();
        final started = Completer<void>();
        adapter.responseHandler = (_) {
          started.complete();
          return response.future;
        };
        final pending = load();
        final assertion = expectLater(
          pending,
          throwsA(isA<SessionSuperseded>()),
        );
        await started.future;
        await storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'test-access-B',
            refreshToken: 'test-refresh-B',
          ),
        );
        response.complete(
          FakeHttpResponse(
            statusCode: lateError ? 500 : 200,
            body: lateError ? {} : [recipeJson()],
          ),
        );
        await assertion;
        expect(storage.accessToken, 'test-access-B');
        expect(storage.refreshToken, 'test-refresh-B');
      },
    );
  }
}

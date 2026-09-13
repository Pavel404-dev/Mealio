import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  const firstItemJson = {
    'id': 'pantry-1',
    'user_id': 'user-1',
    'ingredient_id': 'ingredient-1',
    'quantity_g': '250.00',
    'expires_at': null,
    'created_at': '2026-09-10T10:00:00Z',
    'updated_at': '2026-09-10T10:00:00Z',
    'ingredient': {
      'id': 'ingredient-1',
      'name': 'Oats',
      'category': 'grain',
      'created_at': '2026-09-01T10:00:00Z',
      'nutrition_value': {
        'id': 'nutrition-1',
        'ingredient_id': 'ingredient-1',
        'calories': '389.00',
        'protein_g': '16.90',
        'carbs_g': '66.30',
        'fat_g': '6.90',
        'portion_g': '100.00',
      },
    },
  };
  const secondItemJson = {
    'id': 'pantry-2',
    'user_id': 'user-1',
    'ingredient_id': 'ingredient-2',
    'quantity_g': '500.00',
    'expires_at': null,
    'created_at': '2026-09-09T10:00:00Z',
    'updated_at': '2026-09-09T10:00:00Z',
    'ingredient': {
      'id': 'ingredient-2',
      'name': 'Rice',
      'category': null,
      'created_at': '2026-09-01T10:00:00Z',
      'nutrition_value': null,
    },
  };

  late FakeHttpClientAdapter adapter;
  late PantryRepository repository;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    repository = PantryRepository(apiClient: ApiClient(createFakeDio(adapter)));
  });

  Future<void> expectFailure(PantryFailureType type) async {
    await expectLater(
      repository.getPantry(),
      throwsA(
        isA<PantryFailure>().having((failure) => failure.type, 'type', type),
      ),
    );
  }

  test('GETs /pantry exactly once and maps an empty list', () async {
    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: []));

    final items = await repository.getPantry();

    expect(items, isEmpty);
    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.method, 'GET');
    expect(adapter.requests.single.path, '/pantry');
    expect(adapter.requests.single.data, isNull);
  });

  test('preserves backend order and parses nested nutrition', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: [firstItemJson, secondItemJson],
      ),
    );

    final items = await repository.getPantry();

    expect(items.map((item) => item.id), ['pantry-1', 'pantry-2']);
    expect(items.first.ingredient.nutritionValue?.proteinG, 16.9);
    expect(items.last.ingredient.nutritionValue, isNull);
  });

  test('maps a non-list root to unexpected', () async {
    adapter.enqueue(
      const FakeHttpResponse(statusCode: 200, body: {'items': []}),
    );

    await expectFailure(PantryFailureType.unexpected);
  });

  test('maps a malformed item to unexpected', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: [
          {'id': 'incomplete'},
        ],
      ),
    );

    await expectFailure(PantryFailureType.unexpected);
  });

  test('maps connection errors to connection', () async {
    adapter.enqueue(
      const FakeHttpResponse.error(DioExceptionType.connectionError),
    );

    await expectFailure(PantryFailureType.connection);
  });

  test('maps all timeout errors to connection', () async {
    for (final type in const [
      DioExceptionType.connectionTimeout,
      DioExceptionType.sendTimeout,
      DioExceptionType.receiveTimeout,
      DioExceptionType.transformTimeout,
    ]) {
      adapter.enqueue(FakeHttpResponse.error(type));
      await expectFailure(PantryFailureType.connection);
    }
  });

  test('maps 500 and final 401 responses to backend', () async {
    for (final statusCode in [500, 401]) {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: statusCode,
          body: const {'detail': 'must not be exposed'},
        ),
      );
      await expectFailure(PantryFailureType.backend);
    }
  });

  test('rejects an unexpected non-200 success response', () async {
    adapter.enqueue(const FakeHttpResponse(statusCode: 201, body: []));

    await expectFailure(PantryFailureType.unexpected);
  });

  test(
    'maps non-response list failures to the list unexpected message',
    () async {
      for (final type in const [
        DioExceptionType.badCertificate,
        DioExceptionType.cancel,
        DioExceptionType.unknown,
      ]) {
        adapter.enqueue(FakeHttpResponse.error(type));
        await expectLater(
          repository.getPantry(),
          throwsA(
            isA<PantryFailure>()
                .having(
                  (failure) => failure.type,
                  'type',
                  PantryFailureType.unexpected,
                )
                .having(
                  (failure) => failure.message,
                  'message',
                  'Unable to load your pantry. Please try again.',
                ),
          ),
        );
      }
    },
  );

  group('ingredient search', () {
    Future<void> expectSearchFailure(PantryFailureType type) async {
      await expectLater(
        repository.searchIngredients(),
        throwsA(
          isA<PantryFailure>().having((failure) => failure.type, 'type', type),
        ),
      );
    }

    test('GETs /ingredients with trimmed search and pagination', () async {
      adapter.enqueue(
        FakeHttpResponse(statusCode: 200, body: [firstItemJson['ingredient']]),
      );

      final ingredients = await repository.searchIngredients(
        search: '  Oats  ',
      );

      expect(ingredients.single.name, 'Oats');
      final request = adapter.requests.single;
      expect(request.method, 'GET');
      expect(request.path, '/ingredients');
      expect(request.queryParameters, {
        'search': 'Oats',
        'limit': 50,
        'offset': 0,
      });
    });

    test('omits blank search and parses an empty list', () async {
      adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: []));

      expect(await repository.searchIngredients(search: '   '), isEmpty);
      expect(adapter.requests.single.queryParameters, {
        'limit': 50,
        'offset': 0,
      });
    });

    test('maps malformed roots and items to unexpected', () async {
      for (final body in <Object?>[
        {'items': []},
        [
          {'id': 'incomplete'},
        ],
      ]) {
        adapter.enqueue(FakeHttpResponse(statusCode: 200, body: body));
        await expectSearchFailure(PantryFailureType.unexpected);
      }
    });

    test('maps connection, timeout, backend, and final 401 safely', () async {
      for (final type in const [
        DioExceptionType.connectionError,
        DioExceptionType.receiveTimeout,
      ]) {
        adapter.enqueue(FakeHttpResponse.error(type));
        await expectSearchFailure(PantryFailureType.connection);
      }
      for (final status in [500, 401]) {
        adapter.enqueue(FakeHttpResponse(statusCode: status, body: const {}));
        await expectSearchFailure(
          status == 401
              ? PantryFailureType.authentication
              : PantryFailureType.backend,
        );
      }
    });

    test('rejects unexpected success status', () async {
      adapter.enqueue(const FakeHttpResponse(statusCode: 201, body: []));
      await expectSearchFailure(PantryFailureType.unexpected);
    });

    test(
      'maps non-response failures to the search unexpected message',
      () async {
        for (final type in const [
          DioExceptionType.badCertificate,
          DioExceptionType.cancel,
          DioExceptionType.unknown,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectLater(
            repository.searchIngredients(),
            throwsA(
              isA<PantryFailure>()
                  .having(
                    (failure) => failure.type,
                    'type',
                    PantryFailureType.unexpected,
                  )
                  .having(
                    (failure) => failure.message,
                    'message',
                    'Unable to load ingredients. Please try again.',
                  ),
            ),
          );
        }
      },
    );
  });

  group('pantry create', () {
    Future<void> expectCreateFailure(PantryFailureType type) async {
      await expectLater(
        repository.addPantryItem(
          ingredientId: 'ingredient-1',
          quantityG: '500.25',
        ),
        throwsA(
          isA<PantryFailure>().having((failure) => failure.type, 'type', type),
        ),
      );
    }

    test('POSTs exact decimal-safe body with unset expiry', () async {
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 201, body: firstItemJson),
      );

      final item = await repository.addPantryItem(
        ingredientId: 'ingredient-1',
        quantityG: '500.25',
      );

      expect(item.id, 'pantry-1');
      final request = adapter.requests.single;
      expect(request.method, 'POST');
      expect(request.path, '/pantry');
      expect(request.data, {
        'ingredient_id': 'ingredient-1',
        'quantity_g': '500.25',
        'expires_at': null,
      });
      expect((request.data as Map)['quantity_g'], isA<String>());
    });

    test('encodes selected expiry as UTC ISO-8601', () async {
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 201, body: firstItemJson),
      );

      await repository.addPantryItem(
        ingredientId: 'ingredient-1',
        quantityG: '1',
        expiresAt: DateTime.parse('2026-10-01T02:00:00+02:00'),
      );

      expect(
        (adapter.requests.single.data as Map)['expires_at'],
        '2026-10-01T00:00:00.000Z',
      );
    });

    test('maps create status failures safely', () async {
      for (final entry in const {
        401: PantryFailureType.authentication,
        404: PantryFailureType.ingredientUnavailable,
        409: PantryFailureType.duplicate,
        422: PantryFailureType.validation,
        500: PantryFailureType.backend,
      }.entries) {
        adapter.enqueue(
          FakeHttpResponse(statusCode: entry.key, body: const {}),
        );
        await expectCreateFailure(entry.value);
      }
    });

    test('maps connection and timeout to connection', () async {
      for (final type in const [
        DioExceptionType.connectionError,
        DioExceptionType.sendTimeout,
      ]) {
        adapter.enqueue(FakeHttpResponse.error(type));
        await expectCreateFailure(PantryFailureType.connection);
      }
    });

    test('rejects malformed and unexpected success responses', () async {
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 201, body: {'id': 'incomplete'}),
      );
      await expectCreateFailure(PantryFailureType.unexpected);
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 200, body: firstItemJson),
      );
      await expectCreateFailure(PantryFailureType.unexpected);
    });

    test(
      'maps non-response failures to the create unexpected message',
      () async {
        for (final type in const [
          DioExceptionType.badCertificate,
          DioExceptionType.cancel,
          DioExceptionType.unknown,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectLater(
            repository.addPantryItem(
              ingredientId: 'ingredient-1',
              quantityG: '500.25',
            ),
            throwsA(
              isA<PantryFailure>()
                  .having(
                    (failure) => failure.type,
                    'type',
                    PantryFailureType.unexpected,
                  )
                  .having(
                    (failure) => failure.message,
                    'message',
                    'Unable to add this ingredient. Please try again.',
                  ),
            ),
          );
        }
      },
    );
  });

  group('pantry update', () {
    Future<void> expectUpdateFailure(PantryFailureType type) async {
      await expectLater(
        repository.updatePantryItem(
          pantryItemId: 'pantry-1',
          quantityG: '500.25',
        ),
        throwsA(
          isA<PantryFailure>().having((failure) => failure.type, 'type', type),
        ),
      );
    }

    test('PATCHes exact decimal-safe body and parses the response', () async {
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 200, body: firstItemJson),
      );

      final item = await repository.updatePantryItem(
        pantryItemId: 'pantry-1',
        quantityG: '500.25',
      );

      expect(item.id, 'pantry-1');
      final request = adapter.requests.single;
      expect(request.method, 'PATCH');
      expect(request.path, '/pantry/pantry-1');
      expect(request.data, {'quantity_g': '500.25', 'expires_at': null});
      expect((request.data as Map)['quantity_g'], isA<String>());
    });

    test('encodes expiry as UTC and sends null to clear it', () async {
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 200, body: firstItemJson),
      );
      await repository.updatePantryItem(
        pantryItemId: 'pantry-1',
        quantityG: '1',
        expiresAt: DateTime.parse('2026-10-01T02:00:00+02:00'),
      );
      expect(
        (adapter.requests.single.data as Map)['expires_at'],
        '2026-10-01T00:00:00.000Z',
      );

      adapter.enqueue(
        const FakeHttpResponse(statusCode: 200, body: firstItemJson),
      );
      await repository.updatePantryItem(
        pantryItemId: 'pantry-1',
        quantityG: '1',
      );
      expect((adapter.requests.last.data as Map)['expires_at'], isNull);
    });

    test(
      'maps update response failures to safe operation-specific errors',
      () async {
        const cases = {
          401: (
            type: PantryFailureType.authentication,
            message: 'Your session is no longer valid. Please sign in again.',
          ),
          404: (
            type: PantryFailureType.pantryItemUnavailable,
            message: 'This pantry item is no longer available.',
          ),
          422: (
            type: PantryFailureType.validation,
            message: 'Check the entered values and try again.',
          ),
          500: (
            type: PantryFailureType.backend,
            message: 'Unable to update this pantry item. Please try again.',
          ),
        };
        for (final entry in cases.entries) {
          adapter.enqueue(
            FakeHttpResponse(
              statusCode: entry.key,
              body: const {'detail': 'must not be exposed'},
            ),
          );
          await expectLater(
            repository.updatePantryItem(
              pantryItemId: 'pantry-1',
              quantityG: '500.25',
            ),
            throwsA(
              isA<PantryFailure>()
                  .having((failure) => failure.type, 'type', entry.value.type)
                  .having(
                    (failure) => failure.message,
                    'message',
                    entry.value.message,
                  ),
            ),
          );
        }
      },
    );

    test(
      'maps malformed, unexpected, and non-response update failures safely',
      () async {
        for (final body in <Object?>[
          {'id': 'incomplete'},
          firstItemJson,
        ]) {
          adapter.enqueue(
            FakeHttpResponse(
              statusCode: body == firstItemJson ? 201 : 200,
              body: body,
            ),
          );
          await expectLater(
            repository.updatePantryItem(
              pantryItemId: 'pantry-1',
              quantityG: '1',
            ),
            throwsA(
              isA<PantryFailure>()
                  .having(
                    (failure) => failure.type,
                    'type',
                    PantryFailureType.unexpected,
                  )
                  .having(
                    (failure) => failure.message,
                    'message',
                    'Unable to update this pantry item. Please try again.',
                  ),
            ),
          );
        }
        for (final type in const [
          DioExceptionType.connectionError,
          DioExceptionType.connectionTimeout,
          DioExceptionType.sendTimeout,
          DioExceptionType.receiveTimeout,
          DioExceptionType.transformTimeout,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectUpdateFailure(PantryFailureType.connection);
        }
        for (final type in const [
          DioExceptionType.badCertificate,
          DioExceptionType.cancel,
          DioExceptionType.unknown,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectLater(
            repository.updatePantryItem(
              pantryItemId: 'pantry-1',
              quantityG: '1',
            ),
            throwsA(
              isA<PantryFailure>().having(
                (failure) => failure.message,
                'message',
                'Unable to update this pantry item. Please try again.',
              ),
            ),
          );
        }
      },
    );
  });

  group('pantry delete', () {
    Future<void> expectDeleteFailure(PantryFailureType type) async {
      await expectLater(
        repository.deletePantryItem(pantryItemId: 'pantry-1'),
        throwsA(
          isA<PantryFailure>().having((failure) => failure.type, 'type', type),
        ),
      );
    }

    test(
      'DELETEs the exact path without a request body and accepts 204',
      () async {
        adapter.enqueue(const FakeHttpResponse(statusCode: 204, body: null));
        await repository.deletePantryItem(pantryItemId: 'pantry-1');
        final request = adapter.requests.single;
        expect(request.method, 'DELETE');
        expect(request.path, '/pantry/pantry-1');
        expect(request.data, isNull);
      },
    );

    test(
      'maps delete response failures to safe operation-specific errors',
      () async {
        const cases = {
          401: (
            type: PantryFailureType.authentication,
            message: 'Your session is no longer valid. Please sign in again.',
          ),
          404: (
            type: PantryFailureType.pantryItemUnavailable,
            message: 'This pantry item is no longer available.',
          ),
          422: (
            type: PantryFailureType.backend,
            message: 'Unable to delete this pantry item. Please try again.',
          ),
          500: (
            type: PantryFailureType.backend,
            message: 'Unable to delete this pantry item. Please try again.',
          ),
        };
        for (final entry in cases.entries) {
          adapter.enqueue(
            FakeHttpResponse(
              statusCode: entry.key,
              body: const {'detail': 'must not be exposed'},
            ),
          );
          await expectLater(
            repository.deletePantryItem(pantryItemId: 'pantry-1'),
            throwsA(
              isA<PantryFailure>()
                  .having((failure) => failure.type, 'type', entry.value.type)
                  .having(
                    (failure) => failure.message,
                    'message',
                    entry.value.message,
                  ),
            ),
          );
        }
      },
    );

    test(
      'rejects unexpected and non-response delete failures safely',
      () async {
        adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));
        await expectLater(
          repository.deletePantryItem(pantryItemId: 'pantry-1'),
          throwsA(
            isA<PantryFailure>().having(
              (failure) => failure.message,
              'message',
              'Unable to delete this pantry item. Please try again.',
            ),
          ),
        );
        for (final type in const [
          DioExceptionType.connectionError,
          DioExceptionType.connectionTimeout,
          DioExceptionType.sendTimeout,
          DioExceptionType.receiveTimeout,
          DioExceptionType.transformTimeout,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectDeleteFailure(PantryFailureType.connection);
        }
        for (final type in const [
          DioExceptionType.badCertificate,
          DioExceptionType.cancel,
          DioExceptionType.unknown,
        ]) {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectLater(
            repository.deletePantryItem(pantryItemId: 'pantry-1'),
            throwsA(
              isA<PantryFailure>().having(
                (failure) => failure.message,
                'message',
                'Unable to delete this pantry item. Please try again.',
              ),
            ),
          );
        }
      },
    );
  });
}

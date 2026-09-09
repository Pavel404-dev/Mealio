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
}

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/session_request.dart';
import 'package:mealio/features/meal_plan/data/meal_plan_preview_repository.dart';
import 'package:mealio/features/meal_plan/domain/meal_plan_preview.dart';
import 'package:mealio/features/meal_plan/domain/meal_plan_preview_failure.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;
  late MealPlanPreviewRepository repository;

  final previewRequest = MealPlanPreviewRequest(
    date: DateTime(2026, 12, 21, 23, 30),
    locale: 'uk',
    slots: [MealPlanSlot.lunch, MealPlanSlot.dinner],
  );

  Future<MealPlanPreview> generate() => repository.generate(
    request: previewRequest,
    idempotencyKey: 'preview-key',
    lifetime: storage.sessionLifetime,
    cancelToken: CancelToken(),
  );

  Map<String, dynamic> previewJson({
    String date = '2026-12-21',
    String recipeId = 'c7c69d0e-d6c4-48c6-8b0e-3e068af3e96a',
  }) => {
    'items': [
      for (final slot in previewRequest.slots)
        {
          'recipe_id': recipeId,
          'planned_date': date,
          'meal_type': slot.name,
          'planned_servings': '1.25',
        },
    ],
    'nutrition': {
      'total_calories': '825.00',
      'total_protein_g': '155.00',
      'total_carbs_g': '0.00',
      'total_fat_g': '18.00',
    },
    'target_fit': {'status': 'outside_tolerance', 'tolerance_percent': 10},
  };

  setUp(() {
    adapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();
    repository = MealPlanPreviewRepository(
      apiClient: ApiClient(createFakeDio(adapter), storage: storage),
      storage: storage,
      apiV2BaseUrl: 'http://test.local/api/v2',
    );
  });

  test(
    'posts the scoped v2 request and reads portions and daily totals',
    () async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: previewJson()));
      final result = await generate();
      final wire = adapter.requests.single;
      expect(wire.method, 'POST');
      expect(wire.uri.path, '/api/v2/meal-plans/ai/generate-preview');
      expect(wire.uri.host, 'test.local');
      expect(wire.data, {
        'planned_date': '2026-12-21',
        'locale': 'uk',
        'meal_types': ['lunch', 'dinner'],
      });
      expect(wire.headers['Idempotency-Key'], 'preview-key');
      expect(wire.extra[sessionLifetimeKey], storage.sessionLifetime);
      expect(wire.receiveTimeout, const Duration(seconds: 130));
      expect(result.items.map((item) => item.slot), previewRequest.slots);
      expect(result.items.first.servings, 1.25);
      expect(result.calories, 825);
      expect(result.carbsG, 0);
      expect(result.targetFit, MealPlanTargetFit.outsideTolerance);
    },
  );

  test('rejects an otherwise valid preview for a different day', () async {
    adapter.enqueue(
      FakeHttpResponse(statusCode: 200, body: previewJson(date: '2026-12-22')),
    );
    await expectLater(
      generate(),
      throwsA(
        isA<MealPlanPreviewFailure>().having(
          (error) => error.type,
          'type',
          MealPlanPreviewFailureType.unexpected,
        ),
      ),
    );
  });

  test('rejects a preview with a malformed recipe identifier', () async {
    adapter.enqueue(
      FakeHttpResponse(statusCode: 200, body: previewJson(recipeId: '..')),
    );
    await expectLater(
      generate(),
      throwsA(
        isA<MealPlanPreviewFailure>().having(
          (failure) => failure.type,
          'type',
          MealPlanPreviewFailureType.unexpected,
        ),
      ),
    );
  });

  for (final (status, hasRetryAfter, type) in const [
    (401, false, MealPlanPreviewFailureType.authentication),
    (409, true, MealPlanPreviewFailureType.inProgress),
    (409, false, MealPlanPreviewFailureType.inputsChanged),
    (422, false, MealPlanPreviewFailureType.noEligibleRecipes),
    (429, true, MealPlanPreviewFailureType.rateLimited),
    (503, false, MealPlanPreviewFailureType.providerUnavailable),
  ]) {
    test('maps HTTP $status (Retry-After $hasRetryAfter) to $type', () async {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: status,
          headers: {
            if (hasRetryAfter) 'retry-after': ['1'],
          },
          body: {'detail': 'Raw server message'},
        ),
      );
      await expectLater(
        generate(),
        throwsA(
          isA<MealPlanPreviewFailure>().having(
            (error) => error.type,
            'type',
            type,
          ),
        ),
      );
    });
  }
}

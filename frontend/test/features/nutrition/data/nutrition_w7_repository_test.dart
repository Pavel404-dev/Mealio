import 'dart:async';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/auth_interceptor.dart';
import 'package:mealio/core/network/token_refresh_coordinator.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/nutrition/data/nutrition_repository.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeHttpClientAdapter refresh;
  late FakeSecureStorageService storage;
  late NutritionRepository repository;
  late Dio dio;
  setUp(() {
    adapter = FakeHttpClientAdapter();
    refresh = FakeHttpClientAdapter();
    storage = FakeSecureStorageService(
      accessToken: 'synthetic-a',
      refreshToken: 'synthetic-r',
    );
    dio = createFakeDio(adapter);
    repository = NutritionRepository(
      apiClient: ApiClient(dio, storage: storage),
      storage: storage,
    );
  });
  void auth() => dio.interceptors.add(
    AuthInterceptor(
      dio: dio,
      storage: storage,
      refreshCoordinator: TokenRefreshCoordinator(
        refreshDio: createFakeDio(refresh),
        storage: storage,
        onSessionInvalidated: () {},
      ),
    ),
  );
  Future<Object?> request(String action, [int? owner]) => action == 'calculate'
      ? repository.calculate(
          lifetime: owner ?? storage.sessionLifetime,
          date: DateTime.parse('2026-10-05T00:30:00+02:00'),
        )
      : repository.save(
          lifetime: owner ?? storage.sessionLifetime,
          changes: action == 'confirm'
              ? NutritionPatch.targets(
                  const NutritionTargets(
                    calories: 3204,
                    protein: 160,
                    carbs: 400,
                    fat: 107,
                  ),
                )
              : NutritionPatch.food(
                  likes: const NutritionChange([' rice ', '', 'rice']),
                ),
        );
  Object body(String action) =>
      action == 'calculate' ? calculationJson() : nutritionJson();

  for (final action in ['preferences', 'calculate', 'confirm']) {
    test('$action exact canonical typed wire request', () async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: body(action)));
      await request(action);
      expect(
        adapter.requests.single.method,
        action == 'calculate' ? 'POST' : 'PATCH',
      );
      expect(
        adapter.requests.single.path,
        '/user-preferences/nutrition${action == 'calculate' ? '/calculate' : ''}',
      );
      expect(adapter.requests.single.data, switch (action) {
        'calculate' => {
          'calculation_date': '2026-10-04',
          'rules_version': 'mealio-nutrition-v1',
        },
        'confirm' => {
          'daily_calories_target': 3204,
          'daily_protein_target_g': 160,
          'daily_carbs_target_g': 400,
          'daily_fat_target_g': 107,
        },
        _ => {
          'liked_ingredients': ['rice', 'rice'],
        },
      });
    });
    for (final status in [401, 422, 429, 500]) {
      test(
        '$action maps $status without private detail or compensation',
        () async {
          adapter.enqueue(
            FakeHttpResponse(
              statusCode: status,
              body: {'detail': 'synthetic-private'},
            ),
          );
          final type = switch (status) {
            401 => NutritionFailureType.authentication,
            422 => NutritionFailureType.validation,
            429 => NutritionFailureType.rateLimited,
            _ => NutritionFailureType.unexpected,
          };
          await expectLater(
            request(action),
            throwsA(
              isA<NutritionFailure>()
                  .having((f) => f.type, 'type', type)
                  .having(
                    (f) => f.toString(),
                    'safe text',
                    isNot(contains('synthetic-private')),
                  ),
            ),
          );
          expect(adapter.requests, hasLength(1));
        },
      );
    }
    test('$action connection timeout keeps retry explicit', () async {
      adapter.enqueue(FakeHttpResponse.error(DioExceptionType.receiveTimeout));
      await expectLater(
        request(action),
        throwsA(
          isA<NutritionFailure>().having(
            (f) => f.type,
            'type',
            NutritionFailureType.connection,
          ),
        ),
      );
      expect(adapter.requests, hasLength(1));
    });
    test('$action final ownership check rejects stale dispatch', () async {
      final owner = storage.sessionLifetime;
      await storage.deleteTokenPair();
      await expectLater(
        request(action, owner),
        throwsA(isA<SessionSuperseded>()),
      );
      expect(adapter.requests, isEmpty);
    });
    test(
      '$action lifetime cannot change during credential preparation',
      () async {
        auth();
        final started = Completer<void>();
        final read = Completer<String?>();
        storage.accessReadStarted = started;
        storage.pendingRead = read;
        final assertion = expectLater(
          request(action),
          throwsA(isA<SessionSuperseded>()),
        );
        await started.future;
        final login = storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'synthetic-b',
            refreshToken: 'synthetic-new',
          ),
        );
        read.complete('synthetic-a');
        await login;
        await assertion;
        expect(adapter.requests, isEmpty);
      },
    );
    for (final sameUser in [false, true]) {
      for (final status in [200, 401, 500]) {
        test(
          '$action late $status after ${sameUser ? 'A→A' : 'A→B'} does not publish/refresh/replay',
          () async {
            auth();
            final started = Completer<void>();
            final response = Completer<FakeHttpResponse>();
            adapter.responseHandler = (_) {
              started.complete();
              return response.future;
            };
            final assertion = expectLater(
              request(action),
              throwsA(isA<SessionSuperseded>()),
            );
            await started.future;
            await storage.writeTokenPair(
              AuthTokenPair(
                accessToken: sameUser ? 'synthetic-a' : 'synthetic-b',
                refreshToken: 'synthetic-new',
              ),
            );
            response.complete(
              FakeHttpResponse(statusCode: status, body: body(action)),
            );
            await assertion;
            expect(adapter.requests, hasLength(1));
            expect(refresh.requests, isEmpty);
            expect(storage.refreshToken, 'synthetic-new');
          },
        );
      }
    }
  }
  test('paired money clearing survives actual JSON PATCH', () async {
    for (final change in [
      const NutritionChange(NutritionBudget('50,12', 'eur')),
      const NutritionChange<NutritionBudget?>(null),
    ]) {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: nutritionJson()));
      await repository.save(
        lifetime: storage.sessionLifetime,
        changes: NutritionPatch.practical(budget: change),
      );
    }
    expect(adapter.requests[0].data, {
      'weekly_food_budget_amount': '50.12',
      'budget_currency': 'EUR',
    });
    expect(adapter.requests[1].data, {
      'weekly_food_budget_amount': null,
      'budget_currency': null,
    });
  });
  test(
    'absent likes is a safe compatibility failure, not a saved empty list',
    () async {
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: 200,
          body: nutritionJson()..remove('liked_ingredients'),
        ),
      );
      await expectLater(
        repository.load(lifetime: storage.sessionLifetime),
        throwsA(
          isA<NutritionFailure>().having(
            (f) => f.type,
            'type',
            NutritionFailureType.unexpected,
          ),
        ),
      );
    },
  );
  test(
    'malformed and unknown calculation outcomes expose safe retry failure',
    () async {
      for (final response in [
        {},
        calculationJson()..['status'] = 'future',
        {
          'status': 'unsupported_profile',
          'result': null,
          'reason_codes': ['future'],
          'calculation_date': '2026-10-04',
          'rules_version': NutritionCalculation.rulesVersion,
        },
      ]) {
        adapter.enqueue(FakeHttpResponse(statusCode: 200, body: response));
        await expectLater(
          request('calculate'),
          throwsA(
            isA<NutritionFailure>().having(
              (f) => f.type,
              'type',
              NutritionFailureType.unexpected,
            ),
          ),
        );
      }
    },
  );
}

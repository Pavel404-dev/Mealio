import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/auth_interceptor.dart';
import 'package:mealio/core/network/token_refresh_coordinator.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/nutrition/data/nutrition_repository.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;
  late NutritionRepository repository;
  late Dio dio;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService(
      accessToken: 'synthetic-access-a',
      refreshToken: 'synthetic-refresh-a',
    );
    dio = createFakeDio(adapter);
    repository = NutritionRepository(
      apiClient: ApiClient(dio, storage: storage),
      storage: storage,
    );
  });

  Future<NutritionProfile> request(bool save) => save
      ? repository.save(
          lifetime: storage.sessionLifetime,
          changes: NutritionPatch.formula({NutritionField.weight: '78,40'}),
        )
      : repository.load(lifetime: storage.sessionLifetime);

  test(
    'GET only reads canonical route and decodes exact nullable strings',
    () async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: nutritionJson()));
      final profile = await request(false);
      expect(adapter.requests.single.method, 'GET');
      expect(
        adapter.requests.single.uri.path,
        '/api/v1/user-preferences/nutrition',
      );
      expect(adapter.requests.single.data, isNull);
      expect(profile.values[NutritionField.goal], 'maintain');
      expect(profile.values[NutritionField.weight], isNull);
    },
  );

  test(
    'PATCH subset preserves unrelated profile and exact comma/point scale',
    () async {
      final server = nutritionJson(full: true);
      final before = Map.of(server);
      adapter.responseHandler = (options) {
        server.addAll(options.data as Map<String, dynamic>);
        return FakeHttpResponse(statusCode: 200, body: server);
      };
      final result = await repository.save(
        lifetime: storage.sessionLifetime,
        changes: NutritionPatch.formula({
          NutritionField.height: '193,0',
          NutritionField.weight: '78,40',
          NutritionField.birthDate: '2000-02-29',
        }),
      );
      final sent = adapter.requests.single;
      expect(sent.method, 'PATCH');
      expect(sent.uri.path, '/api/v1/user-preferences/nutrition');
      expect(sent.data, {
        'height_cm': '193.0',
        'weight_kg': '78.40',
        'birth_date': '2000-02-29',
      });
      expect(result.values[NutritionField.weight], '78.40');
      for (final entry in before.entries) {
        if (!(sent.data as Map).containsKey(entry.key)) {
          expect(server[entry.key], entry.value);
        }
      }
    },
  );

  for (final save in [false, true]) {
    for (final status in [401, 422, 429, 500, 503]) {
      test(
        '${save ? 'PATCH' : 'GET'} safe $status without server detail',
        () async {
          adapter.enqueue(
            FakeHttpResponse(
              statusCode: status,
              body: {'detail': 'synthetic-private-detail'},
            ),
          );
          final type = switch (status) {
            401 => NutritionFailureType.authentication,
            422 => NutritionFailureType.validation,
            429 => NutritionFailureType.rateLimited,
            _ => NutritionFailureType.unexpected,
          };
          await expectLater(
            request(save),
            throwsA(
              isA<NutritionFailure>()
                  .having((e) => e.type, 'type', type)
                  .having(
                    (e) => e.toString(),
                    'safe text',
                    isNot(contains('synthetic-private-detail')),
                  ),
            ),
          );
        },
      );
    }
    for (final type in [
      DioExceptionType.connectionTimeout,
      DioExceptionType.receiveTimeout,
      DioExceptionType.sendTimeout,
      DioExceptionType.connectionError,
    ]) {
      test(
        '${save ? 'PATCH' : 'GET'} maps $type without compensation',
        () async {
          adapter.enqueue(FakeHttpResponse.error(type));
          await expectLater(
            request(save),
            throwsA(
              isA<NutritionFailure>().having(
                (e) => e.type,
                'type',
                NutritionFailureType.connection,
              ),
            ),
          );
          expect(adapter.requests, hasLength(1));
        },
      );
    }
    for (final body in [
      null,
      [],
      {},
      nutritionJson()..remove('weight_kg'),
      nutritionJson()..['goal'] = 'unknown',
    ]) {
      test(
        '${save ? 'PATCH' : 'GET'} rejects malformed response $body',
        () async {
          adapter.enqueue(FakeHttpResponse(statusCode: 200, body: body));
          await expectLater(
            request(save),
            throwsA(
              isA<NutritionFailure>().having(
                (e) => e.type,
                'type',
                NutritionFailureType.unexpected,
              ),
            ),
          );
        },
      );
    }
    test('${save ? 'PATCH' : 'GET'} requires 200', () async {
      adapter.enqueue(FakeHttpResponse(statusCode: 201, body: nutritionJson()));
      await expectLater(request(save), throwsA(isA<NutritionFailure>()));
    });
  }

  test(
    'empty PATCH never dispatches; invalid typed input cannot be built',
    () async {
      await expectLater(
        repository.save(
          lifetime: storage.sessionLifetime,
          changes: NutritionPatch.formula({}),
        ),
        throwsA(isA<NutritionFailure>()),
      );
      for (final changes in [
        {NutritionField.height: '170.00'},
        {NutritionField.goal: 'unknown'},
      ]) {
        expect(() => NutritionPatch.formula(changes), throwsFormatException);
      }
      expect(adapter.requests, isEmpty);
    },
  );

  test(
    'same-lifetime refresh retries the exact PATCH with rotated credentials',
    () async {
      final lifetime = storage.sessionLifetime;
      final refresh = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 200,
            body: {
              'access_token': 'synthetic-rotated-access',
              'refresh_token': 'synthetic-rotated-refresh',
              'token_type': 'bearer',
            },
          ),
        );
      adapter
        ..enqueue(const FakeHttpResponse(statusCode: 401, body: {}))
        ..enqueue(
          FakeHttpResponse(
            statusCode: 200,
            body: nutritionJson(full: true)..['weight_kg'] = '78.40',
          ),
        );
      dio.interceptors.add(
        AuthInterceptor(
          dio: dio,
          storage: storage,
          refreshCoordinator: TokenRefreshCoordinator(
            refreshDio: createFakeDio(refresh),
            storage: storage,
            onSessionInvalidated: () => fail('Refresh must keep the lifetime'),
          ),
        ),
      );
      expect((await request(true)).values[NutritionField.weight], '78.40');
      expect(storage.sessionLifetime, lifetime);
      expect(adapter.requests, hasLength(2));
      expect(adapter.requests.first.data, {'weight_kg': '78.40'});
      expect(adapter.requests.last.data, adapter.requests.first.data);
      expect(
        adapter.requests.last.headers['Authorization'],
        'Bearer synthetic-rotated-access',
      );
      expect(refresh.requests, hasLength(1));
    },
  );

  for (final save in [false, true]) {
    test(
      '${save ? 'PATCH' : 'GET'} captured owner rejected before dispatch',
      () async {
        final owner = storage.sessionLifetime;
        await storage.deleteTokenPair();
        await expectLater(
          save
              ? repository.save(
                  lifetime: owner,
                  changes: NutritionPatch.formula({
                    NutritionField.goal: 'gain_weight',
                  }),
                )
              : repository.load(lifetime: owner),
          throwsA(isA<SessionSuperseded>()),
        );
        expect(adapter.requests, isEmpty);
      },
    );

    test(
      '${save ? 'PATCH' : 'GET'} async credential preparation cannot use new login',
      () async {
        final started = Completer<void>();
        final read = Completer<String?>();
        storage.accessReadStarted = started;
        storage.pendingRead = read;
        dio.interceptors.add(
          AuthInterceptor(
            dio: dio,
            storage: storage,
            refreshCoordinator: TokenRefreshCoordinator(
              refreshDio: createFakeDio(FakeHttpClientAdapter()),
              storage: storage,
              onSessionInvalidated: () {},
            ),
          ),
        );
        final pending = request(save);
        final assertion = expectLater(
          pending,
          throwsA(isA<SessionSuperseded>()),
        );
        await started.future;
        final login = storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'synthetic-access-b',
            refreshToken: 'synthetic-refresh-b',
          ),
        );
        read.complete('synthetic-access-a');
        await login;
        await assertion;
        expect(adapter.requests, isEmpty);
      },
    );

    test(
      '${save ? 'PATCH' : 'GET'} late 401 does not refresh/replay for B',
      () async {
        final started = Completer<void>();
        final response = Completer<FakeHttpResponse>();
        final refresh = FakeHttpClientAdapter();
        adapter.responseHandler = (_) {
          started.complete();
          return response.future;
        };
        dio.interceptors.add(
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
        final assertion = expectLater(
          request(save),
          throwsA(isA<SessionSuperseded>()),
        );
        await started.future;
        await storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'synthetic-access-b',
            refreshToken: 'synthetic-refresh-b',
          ),
        );
        response.complete(const FakeHttpResponse(statusCode: 401, body: {}));
        await assertion;
        expect(adapter.requests, hasLength(1));
        expect(refresh.requests, isEmpty);
        expect(storage.accessToken, 'synthetic-access-b');
      },
    );
  }
}

import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/auth_interceptor.dart';
import 'package:mealio/core/network/token_refresh_coordinator.dart';

import '../../helpers/auth_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter appAdapter;
  late FakeHttpClientAdapter refreshAdapter;
  late FakeSecureStorageService storage;
  late int invalidationCount;

  setUp(() {
    appAdapter = FakeHttpClientAdapter();
    refreshAdapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();
    invalidationCount = 0;
  });

  Dio createAuthenticatedDio() {
    final dio = createFakeDio(appAdapter);
    final coordinator = TokenRefreshCoordinator(
      refreshDio: createFakeDio(refreshAdapter),
      storage: storage,
      onSessionInvalidated: () => invalidationCount++,
    );

    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        storage: storage,
        refreshCoordinator: coordinator,
      ),
    );
    return dio;
  }

  test('stored token adds bearer Authorization header', () async {
    storage = FakeSecureStorageService(accessToken: 'stored-token');
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      appAdapter.requests.single.headers['Authorization'],
      'Bearer stored-token',
    );
  });

  test('missing token does not add Authorization header', () async {
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      appAdapter.requests.single.headers.containsKey('Authorization'),
      isFalse,
    );
  });

  test('empty token does not add Authorization header', () async {
    storage = FakeSecureStorageService(accessToken: '   ');
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      appAdapter.requests.single.headers.containsKey('Authorization'),
      isFalse,
    );
  });

  test('token reading is awaited asynchronously', () async {
    final readCompleter = Completer<String?>();
    storage.pendingRead = readCompleter;
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    final requestFuture = dio.get<Object?>('/auth/me');

    expect(appAdapter.requests, isEmpty);

    readCompleter.complete('async-token');
    await requestFuture;

    expect(storage.readCount, 1);
    expect(
      appAdapter.requests.single.headers['Authorization'],
      'Bearer async-token',
    );
  });

  test(
    'public auth requests attach no bearer and never auto refresh',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'stale-token',
        refreshToken: 'refresh-token',
      );
      final dio = createAuthenticatedDio();

      for (final path in const [
        '/auth/login',
        '/auth/register',
        '/auth/refresh',
        '/auth/logout',
        '/auth/email-verification/request',
        '/auth/email-verification/confirm',
      ]) {
        appAdapter.enqueue(
          const FakeHttpResponse(statusCode: 401, body: {'detail': 'rejected'}),
        );

        await expectLater(
          dio.post<Object?>(path, data: const {}),
          throwsA(isA<DioException>()),
        );

        expect(
          appAdapter.requests.last.headers.containsKey('Authorization'),
          isFalse,
        );
      }

      expect(storage.readCount, 0);
      expect(refreshAdapter.requests, isEmpty);
    },
  );

  test('protected 401 refreshes, stores rotation, and retries once', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );
    final dio = createAuthenticatedDio();

    appAdapter
      ..enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      )
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: {'ok': true}));
    refreshAdapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {
          'access_token': 'new-access',
          'refresh_token': 'new-refresh',
          'token_type': 'bearer',
        },
      ),
    );

    final response = await dio.get<Object?>('/recipes');

    expect(response.statusCode, 200);
    expect(appAdapter.requests, hasLength(2));
    expect(
      appAdapter.requests.first.headers['Authorization'],
      'Bearer old-access',
    );
    expect(
      appAdapter.requests.last.headers['Authorization'],
      'Bearer new-access',
    );
    expect(refreshAdapter.requests, hasLength(1));
    expect(refreshAdapter.requests.single.path, '/auth/refresh');
    expect(refreshAdapter.requests.single.data, {
      'refresh_token': 'old-refresh',
    });
    expect(storage.accessToken, 'new-access');
    expect(storage.refreshToken, 'new-refresh');
    expect(invalidationCount, 0);
  });

  test('second 401 after retry does not refresh again', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );
    final dio = createAuthenticatedDio();

    appAdapter
      ..enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      )
      ..enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'still bad'}),
      );
    refreshAdapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {
          'access_token': 'new-access',
          'refresh_token': 'new-refresh',
          'token_type': 'bearer',
        },
      ),
    );

    await expectLater(
      dio.get<Object?>('/recipes'),
      throwsA(
        isA<DioException>().having(
          (error) => error.response?.statusCode,
          'statusCode',
          401,
        ),
      ),
    );

    expect(appAdapter.requests, hasLength(2));
    expect(refreshAdapter.requests, hasLength(1));
    expect(storage.accessToken, 'new-access');
    expect(storage.refreshToken, 'new-refresh');
    expect(invalidationCount, 0);
  });

  test('delayed second 401 cannot invalidate a newer session', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );
    final dio = createAuthenticatedDio();
    final retryStarted = Completer<void>();
    final releaseRetry401 = Completer<void>();

    appAdapter.responseHandler = (options) async {
      final authorization = options.headers['Authorization'];
      final isRetry = options.extra['mealio_auth_retried'] == true;

      if (authorization == 'Bearer old-access' && !isRetry) {
        return const FakeHttpResponse(
          statusCode: 401,
          body: {'detail': 'expired'},
        );
      }

      if (authorization == 'Bearer refreshed-access' && isRetry) {
        if (!retryStarted.isCompleted) {
          retryStarted.complete();
        }

        await releaseRetry401.future;
        return const FakeHttpResponse(
          statusCode: 401,
          body: {'detail': 'delayed retry rejection'},
        );
      }

      throw StateError(
        'Unexpected auth request: $authorization, retry=$isRetry',
      );
    };

    refreshAdapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {
          'access_token': 'refreshed-access',
          'refresh_token': 'refreshed-refresh',
          'token_type': 'bearer',
        },
      ),
    );

    final oldRequest = dio.get<Object?>('/recipes');

    await retryStarted.future;

    await storage.writeTokenPair(
      const AuthTokenPair(
        accessToken: 'new-session-access',
        refreshToken: 'new-session-refresh',
      ),
    );

    releaseRetry401.complete();

    await expectLater(
      oldRequest,
      throwsA(
        isA<DioException>().having(
          (error) => error.response?.statusCode,
          'statusCode',
          401,
        ),
      ),
    );

    expect(refreshAdapter.requests, hasLength(1));
    expect(storage.accessToken, 'new-session-access');
    expect(storage.refreshToken, 'new-session-refresh');
    expect(invalidationCount, 0);
  });

  test('non-401 network error does not start refresh', () async {
    storage = FakeSecureStorageService(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    );
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(
      const FakeHttpResponse.error(DioExceptionType.connectionError),
    );

    await expectLater(
      dio.get<Object?>('/recipes'),
      throwsA(
        isA<DioException>().having(
          (error) => error.type,
          'type',
          DioExceptionType.connectionError,
        ),
      ),
    );

    expect(refreshAdapter.requests, isEmpty);
  });

  test(
    'refresh network error preserves token pair and invalidation state',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final dio = createAuthenticatedDio();

      appAdapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse.error(DioExceptionType.connectionError),
      );

      await expectLater(
        dio.get<Object?>('/recipes'),
        throwsA(
          isA<DioException>().having(
            (error) => error.type,
            'type',
            DioExceptionType.connectionError,
          ),
        ),
      );

      expect(storage.accessToken, 'old-access');
      expect(storage.refreshToken, 'old-refresh');
      expect(invalidationCount, 0);
    },
  );

  test(
    'refresh server error preserves token pair without invalidation',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final dio = createAuthenticatedDio();

      appAdapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse(
          statusCode: 503,
          body: {'detail': 'temporarily unavailable'},
        ),
      );

      await expectLater(
        dio.get<Object?>('/recipes'),
        throwsA(
          isA<DioException>().having(
            (error) => error.response?.statusCode,
            'statusCode',
            503,
          ),
        ),
      );

      expect(storage.accessToken, 'old-access');
      expect(storage.refreshToken, 'old-refresh');
      expect(invalidationCount, 0);
    },
  );

  test('refresh 401 clears pair and invalidates session', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );
    final dio = createAuthenticatedDio();

    appAdapter.enqueue(
      const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
    );
    refreshAdapter.enqueue(
      const FakeHttpResponse(
        statusCode: 401,
        body: {'detail': 'Invalid refresh token'},
      ),
    );

    await expectLater(
      dio.get<Object?>('/recipes'),
      throwsA(isA<DioException>()),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(invalidationCount, 1);
    expect(refreshAdapter.requests, hasLength(1));
  });

  test(
    'malformed refresh response clears pair and invalidates session',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final dio = createAuthenticatedDio();

      appAdapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse(
          statusCode: 200,
          body: {
            'access_token': 'new-access',
            'refresh_token': '',
            'token_type': 'bearer',
          },
        ),
      );

      await expectLater(
        dio.get<Object?>('/recipes'),
        throwsA(isA<DioException>()),
      );

      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(invalidationCount, 1);
    },
  );

  test(
    'refresh persistence failure clears pair and invalidates session',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
        failAccessWrite: true,
      );
      final dio = createAuthenticatedDio();

      appAdapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse(
          statusCode: 200,
          body: {
            'access_token': 'new-access',
            'refresh_token': 'new-refresh',
            'token_type': 'bearer',
          },
        ),
      );

      await expectLater(
        dio.get<Object?>('/recipes'),
        throwsA(isA<DioException>()),
      );

      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(invalidationCount, 1);
    },
  );

  test('concurrent 401 responses share exactly one refresh', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );
    final dio = createAuthenticatedDio();
    final allInitialRequestsSeen = Completer<void>();
    final refreshStarted = Completer<void>();
    final releaseRefresh = Completer<void>();
    var oldAccessRequests = 0;

    appAdapter.responseHandler = (options) async {
      final authorization = options.headers['Authorization'];
      if (authorization == 'Bearer old-access') {
        oldAccessRequests++;
        if (oldAccessRequests == 3 && !allInitialRequestsSeen.isCompleted) {
          allInitialRequestsSeen.complete();
        }
        await allInitialRequestsSeen.future;
        return const FakeHttpResponse(
          statusCode: 401,
          body: {'detail': 'expired'},
        );
      }

      if (authorization == 'Bearer new-access') {
        return const FakeHttpResponse(statusCode: 200, body: {'ok': true});
      }

      throw StateError('Unexpected Authorization header: $authorization');
    };

    refreshAdapter.responseHandler = (options) async {
      expect(options.path, '/auth/refresh');
      if (!refreshStarted.isCompleted) {
        refreshStarted.complete();
      }
      await releaseRefresh.future;
      return const FakeHttpResponse(
        statusCode: 200,
        body: {
          'access_token': 'new-access',
          'refresh_token': 'new-refresh',
          'token_type': 'bearer',
        },
      );
    };

    final requests = [
      dio.get<Object?>('/recipes'),
      dio.get<Object?>('/pantry'),
      dio.get<Object?>('/meal-plans'),
    ];

    await allInitialRequestsSeen.future;
    await refreshStarted.future;
    expect(refreshAdapter.requests, hasLength(1));

    releaseRefresh.complete();
    final responses = await Future.wait(requests);

    expect(responses.every((response) => response.statusCode == 200), isTrue);
    expect(refreshAdapter.requests, hasLength(1));
    expect(
      appAdapter.requests
          .where(
            (request) =>
                request.headers['Authorization'] == 'Bearer new-access',
          )
          .length,
      3,
    );
  });

  test(
    'delayed stale 401 does not re-rotate when refreshed JWT string is unchanged',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'same-access',
        refreshToken: 'old-refresh',
      );
      final dio = createAuthenticatedDio();
      final secondInitialRequestSeen = Completer<void>();
      final releaseDelayed401 = Completer<void>();
      var initialRequests = 0;

      appAdapter.responseHandler = (options) async {
        final authorization = options.headers['Authorization'];
        final isRetry = options.extra['mealio_auth_retried'] == true;

        if (authorization == 'Bearer same-access' && isRetry) {
          return const FakeHttpResponse(statusCode: 200, body: {'ok': true});
        }

        if (authorization == 'Bearer same-access') {
          initialRequests++;
          if (initialRequests == 1) {
            return const FakeHttpResponse(
              statusCode: 401,
              body: {'detail': 'expired'},
            );
          }

          if (!secondInitialRequestSeen.isCompleted) {
            secondInitialRequestSeen.complete();
          }
          await releaseDelayed401.future;
          return const FakeHttpResponse(
            statusCode: 401,
            body: {'detail': 'delayed expired response'},
          );
        }

        throw StateError('Unexpected Authorization header: $authorization');
      };

      refreshAdapter.enqueue(
        const FakeHttpResponse(
          statusCode: 200,
          body: {
            'access_token': 'same-access',
            'refresh_token': 'new-refresh',
            'token_type': 'bearer',
          },
        ),
      );

      final firstRequest = dio.get<Object?>('/recipes');
      final secondRequest = dio.get<Object?>('/pantry');

      await secondInitialRequestSeen.future;
      expect((await firstRequest).statusCode, 200);
      expect(refreshAdapter.requests, hasLength(1));

      releaseDelayed401.complete();
      expect((await secondRequest).statusCode, 200);

      expect(refreshAdapter.requests, hasLength(1));
      expect(storage.accessToken, 'same-access');
      expect(storage.refreshToken, 'new-refresh');
    },
  );

  test(
    'late refresh response cannot restore a locally removed session',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final dio = createAuthenticatedDio();
      final refreshStarted = Completer<void>();
      final releaseRefresh = Completer<void>();

      appAdapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.responseHandler = (options) async {
        if (options.path == '/auth/logout') {
          return const FakeHttpResponse(statusCode: 204, body: null);
        }

        if (!refreshStarted.isCompleted) {
          refreshStarted.complete();
        }
        await releaseRefresh.future;
        return const FakeHttpResponse(
          statusCode: 200,
          body: {
            'access_token': 'late-access',
            'refresh_token': 'late-refresh',
            'token_type': 'bearer',
          },
        );
      };

      final request = dio.get<Object?>('/recipes');
      await refreshStarted.future;
      await storage.deleteTokenPair();
      releaseRefresh.complete();

      await expectLater(request, throwsA(isA<DioException>()));

      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(invalidationCount, 0);
      expect(
        refreshAdapter.requests.where(
          (request) => request.path == '/auth/refresh',
        ),
        hasLength(1),
      );
      expect(
        refreshAdapter.requests.where(
          (request) => request.path == '/auth/logout',
        ),
        hasLength(1),
      );
    },
  );
}

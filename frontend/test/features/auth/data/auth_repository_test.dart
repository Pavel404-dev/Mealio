import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/auth_interceptor.dart';
import 'package:mealio/core/network/token_refresh_coordinator.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  const userJson = {
    'id': '7c59f60a-8428-4bce-a2bd-bfe7dd10b3af',
    'email': 'pavel@example.com',
    'full_name': 'Pavel Potapenko',
    'created_at': '2026-07-20T10:00:00Z',
    'updated_at': '2026-07-20T10:00:00Z',
  };
  const tokenPairJson = {
    'access_token': 'test-access-token',
    'refresh_token': 'test-refresh-token',
    'token_type': 'bearer',
  };

  late FakeHttpClientAdapter adapter;
  late FakeHttpClientAdapter refreshAdapter;
  late FakeSecureStorageService storage;
  late AuthRepository repository;
  late int invalidationCount;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    refreshAdapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();
    invalidationCount = 0;

    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
  });

  void useAuthenticatedTransport() {
    final dio = createFakeDio(adapter);
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
    repository = AuthRepository(apiClient: ApiClient(dio), storage: storage);
  }

  test('successful login stores token pair and fetches me', () async {
    adapter
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: tokenPairJson))
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));

    final user = await repository.login(
      email: '  pavel@example.com  ',
      password: 'test-password',
    );

    expect(adapter.requests, hasLength(2));
    expect(adapter.requests[0].path, '/auth/login');
    expect(adapter.requests[0].data, {
      'email': 'pavel@example.com',
      'password': 'test-password',
    });
    expect(adapter.requests[1].path, '/auth/me');
    expect(storage.accessToken, 'test-access-token');
    expect(storage.refreshToken, 'test-refresh-token');
    expect(user, testAuthUser);
  });

  test('login 401 maps to invalid credentials and stores no pair', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 401,
        body: {'detail': 'Invalid email or password'},
      ),
    );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'wrong-password'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.invalidCredentials,
        ),
      ),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('login 422 maps to validation error', () async {
    adapter.enqueue(
      const FakeHttpResponse(statusCode: 422, body: {'detail': []}),
    );

    await expectLater(
      repository.login(email: 'invalid', password: 'test-password'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.validation,
        ),
      ),
    );
  });

  test('connection error maps to user-facing connection error', () async {
    adapter.enqueue(
      const FakeHttpResponse.error(DioExceptionType.connectionError),
    );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'test-password'),
      throwsA(
        isA<AuthFailure>()
            .having(
              (failure) => failure.type,
              'type',
              AuthFailureType.connection,
            )
            .having(
              (failure) => failure.message,
              'message',
              'Unable to connect to the server. Please try again.',
            ),
      ),
    );
  });

  test('login rejects missing refresh token without storing session', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {'access_token': 'access', 'token_type': 'bearer'},
      ),
    );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'test-password'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.unexpected,
        ),
      ),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('login rejects empty access token and wrong token type', () async {
    for (final body in const [
      {'access_token': '', 'refresh_token': 'refresh', 'token_type': 'bearer'},
      {
        'access_token': 'access',
        'refresh_token': 'refresh',
        'token_type': 'Bearer',
      },
    ]) {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: body));

      await expectLater(
        repository.login(email: 'pavel@example.com', password: 'test-password'),
        throwsA(isA<AuthFailure>()),
      );
    }

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('login rejects non-map token response', () async {
    adapter.enqueue(
      const FakeHttpResponse(statusCode: 200, body: ['not', 'a', 'map']),
    );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'test-password'),
      throwsA(isA<AuthFailure>()),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('storage failure during login leaves no partial token pair', () async {
    storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
      failAccessWrite: true,
    );
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(
      const FakeHttpResponse(statusCode: 200, body: tokenPairJson),
    );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'test-password'),
      throwsA(isA<AuthFailure>()),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('me failure after saved login pair removes both tokens', () async {
    adapter
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: tokenPairJson))
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 500,
          body: {'detail': 'server error'},
        ),
      );

    await expectLater(
      repository.login(email: 'pavel@example.com', password: 'test-password'),
      throwsA(isA<AuthFailure>()),
    );

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
  });

  test('restoreSession without tokens returns null without network', () async {
    final user = await repository.restoreSession();

    expect(user, isNull);
    expect(adapter.requests, isEmpty);
  });

  test('restoreSession with valid token pair fetches current user', () async {
    storage = FakeSecureStorageService(
      accessToken: 'stored-access',
      refreshToken: 'stored-refresh',
    );
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));

    final user = await repository.restoreSession();

    expect(user, testAuthUser);
    expect(adapter.requests.single.path, '/auth/me');
    expect(storage.accessToken, 'stored-access');
    expect(storage.refreshToken, 'stored-refresh');
  });

  test(
    'expired access with valid refresh restores session automatically',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'expired-access',
        refreshToken: 'valid-refresh',
      );
      useAuthenticatedTransport();
      adapter
        ..enqueue(
          const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
        )
        ..enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));
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

      final user = await repository.restoreSession();

      expect(user, testAuthUser);
      expect(storage.accessToken, 'new-access');
      expect(storage.refreshToken, 'new-refresh');
      expect(refreshAdapter.requests, hasLength(1));
      expect(invalidationCount, 0);
    },
  );

  test(
    'restore keeps token pair when refresh transport is unavailable',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'expired-access',
        refreshToken: 'valid-refresh',
      );
      useAuthenticatedTransport();
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse.error(DioExceptionType.connectionError),
      );

      await expectLater(
        repository.restoreSession(),
        throwsA(
          isA<AuthFailure>().having(
            (failure) => failure.type,
            'type',
            AuthFailureType.connection,
          ),
        ),
      );

      expect(storage.accessToken, 'expired-access');
      expect(storage.refreshToken, 'valid-refresh');
      expect(invalidationCount, 0);
    },
  );

  test(
    'invalid refresh clears pair and restore becomes unauthenticated',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'expired-access',
        refreshToken: 'invalid-refresh',
      );
      useAuthenticatedTransport();
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );
      refreshAdapter.enqueue(
        const FakeHttpResponse(
          statusCode: 401,
          body: {'detail': 'Invalid refresh token'},
        ),
      );

      final user = await repository.restoreSession();

      expect(user, isNull);
      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(invalidationCount, 1);
    },
  );

  test(
    'legacy access-only state is accepted while access remains valid',
    () async {
      storage = FakeSecureStorageService(accessToken: 'legacy-access');
      useAuthenticatedTransport();
      adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));

      final user = await repository.restoreSession();

      expect(user, testAuthUser);
      expect(storage.accessToken, 'legacy-access');
      expect(storage.refreshToken, isNull);
      expect(refreshAdapter.requests, isEmpty);
    },
  );

  test(
    'legacy access-only state clears safely after access is rejected',
    () async {
      storage = FakeSecureStorageService(accessToken: 'legacy-access');
      useAuthenticatedTransport();
      adapter.enqueue(
        const FakeHttpResponse(statusCode: 401, body: {'detail': 'expired'}),
      );

      final user = await repository.restoreSession();

      expect(user, isNull);
      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(refreshAdapter.requests, isEmpty);
      expect(invalidationCount, 1);
    },
  );

  test(
    'refresh-only corrupt state is cleaned without network request',
    () async {
      storage = FakeSecureStorageService(refreshToken: 'orphan-refresh');
      repository = AuthRepository(
        apiClient: ApiClient(createFakeDio(adapter)),
        storage: storage,
      );

      final user = await repository.restoreSession();

      expect(user, isNull);
      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(adapter.requests, isEmpty);
    },
  );

  test('logout sends refresh token then leaves both tokens cleared', () async {
    storage = FakeSecureStorageService(
      accessToken: 'stored-access',
      refreshToken: 'stored-refresh',
    );
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(const FakeHttpResponse(statusCode: 204, body: null));

    await repository.logout();

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.path, '/auth/logout');
    expect(adapter.requests.single.data, {'refresh_token': 'stored-refresh'});
  });

  test('logout without refresh token still clears local session', () async {
    storage = FakeSecureStorageService(accessToken: 'stored-access');
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );

    await repository.logout();

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(adapter.requests, isEmpty);
  });

  test('logout network failure still clears local token pair', () async {
    storage = FakeSecureStorageService(
      accessToken: 'stored-access',
      refreshToken: 'stored-refresh',
    );
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(
      const FakeHttpResponse.error(DioExceptionType.connectionError),
    );

    await repository.logout();

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(adapter.requests, hasLength(1));
  });

  test(
    'successful registration posts normalized data without changing storage',
    () async {
      storage = FakeSecureStorageService(
        accessToken: 'existing-access',
        refreshToken: 'existing-refresh',
      );
      repository = AuthRepository(
        apiClient: ApiClient(createFakeDio(adapter)),
        storage: storage,
      );
      adapter.enqueue(const FakeHttpResponse(statusCode: 201, body: userJson));

      final user = await repository.register(
        email: '  Pavel@Example.COM  ',
        fullName: '  Pavel Potapenko  ',
        password: '  Mealio-password  ',
      );

      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.single.path, '/auth/register');
      expect(adapter.requests.single.data, {
        'email': 'pavel@example.com',
        'full_name': 'Pavel Potapenko',
        'password': '  Mealio-password  ',
      });
      expect(user, testAuthUser);
      expect(storage.readCount, 0);
      expect(storage.refreshReadCount, 0);
      expect(storage.writeCount, 0);
      expect(storage.refreshWriteCount, 0);
      expect(storage.deleteCount, 0);
      expect(storage.refreshDeleteCount, 0);
      expect(storage.accessToken, 'existing-access');
      expect(storage.refreshToken, 'existing-refresh');
    },
  );

  test('registration sends empty full name as null', () async {
    adapter.enqueue(const FakeHttpResponse(statusCode: 201, body: userJson));

    await repository.register(
      email: 'pavel@example.com',
      fullName: '   ',
      password: 'Mealio-password-123',
    );

    expect(adapter.requests.single.data, {
      'email': 'pavel@example.com',
      'full_name': null,
      'password': 'Mealio-password-123',
    });
  });

  test('registration 409 maps to duplicate email', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 409,
        body: {'detail': 'User with this email already exists'},
      ),
    );

    await expectLater(
      repository.register(
        email: 'pavel@example.com',
        password: 'Mealio-password-123',
      ),
      throwsA(
        isA<AuthFailure>()
            .having(
              (failure) => failure.type,
              'type',
              AuthFailureType.duplicateEmail,
            )
            .having(
              (failure) => failure.message,
              'message',
              'An account with this email already exists.',
            ),
      ),
    );
  });

  test('registration 422 maps to safe validation error', () async {
    adapter.enqueue(
      const FakeHttpResponse(statusCode: 422, body: {'detail': []}),
    );

    await expectLater(
      repository.register(email: 'invalid', password: 'Mealio-password-123'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.registrationValidation,
        ),
      ),
    );
  });

  test(
    'registration connection failure maps to safe connection error',
    () async {
      adapter.enqueue(
        const FakeHttpResponse.error(DioExceptionType.connectionError),
      );

      await expectLater(
        repository.register(
          email: 'pavel@example.com',
          password: 'Mealio-password-123',
        ),
        throwsA(
          isA<AuthFailure>().having(
            (failure) => failure.type,
            'type',
            AuthFailureType.connection,
          ),
        ),
      );
    },
  );

  test('malformed registration response is handled safely', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 201,
        body: {'email': 'pavel@example.com'},
      ),
    );

    await expectLater(
      repository.register(
        email: 'pavel@example.com',
        password: 'Mealio-password-123',
      ),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.unexpected,
        ),
      ),
    );
  });

  test('unexpected registration success status is rejected safely', () async {
    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));

    await expectLater(
      repository.register(
        email: 'pavel@example.com',
        password: 'Mealio-password-123',
      ),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.unexpected,
        ),
      ),
    );
  });
}

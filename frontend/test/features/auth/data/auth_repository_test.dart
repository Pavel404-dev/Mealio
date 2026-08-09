import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/api_client.dart';
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

  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;
  late AuthRepository repository;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();

    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
  });

  test('successful login posts credentials, saves token, fetches me', () async {
    adapter
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 200,
          body: {'access_token': 'test-access-token', 'token_type': 'bearer'},
        ),
      )
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
    expect(storage.writeCount, 1);
    expect(storage.lastWrittenToken, 'test-access-token');
    expect(user, testAuthUser);
  });

  test('login 401 maps to invalid credentials and stores no token', () async {
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

    expect(storage.writeCount, 0);
    expect(storage.token, isNull);
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

  test('malformed login response is handled safely', () async {
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {'access_token': '', 'token_type': 'bearer'},
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

    expect(storage.writeCount, 0);
  });

  test('me failure after saved login token removes token', () async {
    adapter
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 200,
          body: {'access_token': 'test-access-token', 'token_type': 'bearer'},
        ),
      )
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

    expect(storage.writeCount, 1);
    expect(storage.deleteCount, 1);
    expect(storage.token, isNull);
  });

  test(
    'restoreSession without token returns null without network request',
    () async {
      final user = await repository.restoreSession();

      expect(user, isNull);
      expect(adapter.requests, isEmpty);
    },
  );

  test('restoreSession with valid token fetches current user', () async {
    storage = FakeSecureStorageService(token: 'stored-token');
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: userJson));

    final user = await repository.restoreSession();

    expect(user, testAuthUser);
    expect(adapter.requests.single.path, '/auth/me');
    expect(storage.deleteCount, 0);
  });

  test('restoreSession with invalid token deletes token', () async {
    storage = FakeSecureStorageService(token: 'invalid-token');
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );
    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 401,
        body: {'detail': 'Could not validate credentials'},
      ),
    );

    final user = await repository.restoreSession();

    expect(user, isNull);
    expect(storage.deleteCount, 1);
    expect(storage.token, isNull);
  });

  test('restoreSession treats empty stored token as no session', () async {
    storage = FakeSecureStorageService(token: '   ');
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );

    final user = await repository.restoreSession();

    expect(user, isNull);
    expect(storage.deleteCount, 1);
    expect(adapter.requests, isEmpty);
  });

  test('logout deletes access token', () async {
    storage = FakeSecureStorageService(token: 'stored-token');
    repository = AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: storage,
    );

    await repository.logout();

    expect(storage.deleteCount, 1);
    expect(storage.token, isNull);
  });

  test(
    'successful registration posts normalized data without changing storage',
    () async {
      storage = FakeSecureStorageService(token: 'existing-token');
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
      expect(storage.writeCount, 0);
      expect(storage.deleteCount, 0);
      expect(storage.lastWrittenToken, isNull);
      expect(storage.token, 'existing-token');
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

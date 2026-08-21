import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  AuthRepository createRepository(FakeHttpClientAdapter adapter) {
    return AuthRepository(
      apiClient: ApiClient(createFakeDio(adapter)),
      storage: FakeSecureStorageService(),
    );
  }

  test(
    'password reset request accepts generic 202 and normalizes email',
    () async {
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 202,
            body: {
              'message':
                  'If an account with that email exists, password reset instructions have been sent.',
            },
          ),
        );
      final repository = createRepository(adapter);

      await repository.requestPasswordReset(email: '  PAVEL@EXAMPLE.COM  ');

      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.single.path, '/auth/password-reset/request');
      expect(adapter.requests.single.data, {'email': 'pavel@example.com'});
    },
  );

  test('password reset request maps backend failure safely', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 503,
          body: {'detail': 'Password reset delivery is not configured'},
        ),
      );
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestPasswordReset(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.passwordResetRequest,
        ),
      ),
    );
  });

  test('password reset request maps transport failure', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestPasswordReset(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.connection,
        ),
      ),
    );
  });

  test('password reset confirm preserves opaque token and password', () async {
    const token = 'opaque-password-reset-token';
    const password = '  Mealio-new-password  ';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 204, body: null));
    final repository = createRepository(adapter);

    await repository.confirmPasswordReset(token: token, newPassword: password);

    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.path, '/auth/password-reset/confirm');
    expect(adapter.requests.single.data, {
      'token': token,
      'new_password': password,
    });
  });

  test(
    'password reset confirm maps generic 400 without leaking token',
    () async {
      const token = 'secret-reset-token-that-must-not-leak';
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 400,
            body: {'detail': 'Invalid or expired password reset token.'},
          ),
        );
      final repository = createRepository(adapter);

      try {
        await repository.confirmPasswordReset(
          token: token,
          newPassword: 'Mealio-new-password-123',
        );
        fail('Expected AuthFailure');
      } on AuthFailure catch (failure) {
        expect(failure.type, AuthFailureType.passwordResetInvalid);
        expect(failure.message, isNot(contains(token)));
        expect(failure.toString(), isNot(contains(token)));
      }
    },
  );

  test('password reset confirm maps 422 to safe validation failure', () async {
    const token = 'validation-secret-reset-token';
    const password = 'invalid';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 422, body: {'detail': []}));
    final repository = createRepository(adapter);

    try {
      await repository.confirmPasswordReset(
        token: token,
        newPassword: password,
      );
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.passwordResetValidation);
      expect(failure.message, isNot(contains(token)));
      expect(failure.message, isNot(contains(password)));
      expect(failure.toString(), isNot(contains(token)));
    }
  });

  test(
    'password reset confirm maps transport failure without leaking token',
    () async {
      const token = 'network-secret-reset-token';
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse.error(DioExceptionType.connectionError),
        );
      final repository = createRepository(adapter);

      try {
        await repository.confirmPasswordReset(
          token: token,
          newPassword: 'Mealio-new-password-123',
        );
        fail('Expected AuthFailure');
      } on AuthFailure catch (failure) {
        expect(failure.type, AuthFailureType.connection);
        expect(failure.message, isNot(contains(token)));
        expect(failure.toString(), isNot(contains(token)));
      }
    },
  );

  test('unexpected successful reset status maps to safe failure', () async {
    const token = 'unexpected-reset-token';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: {}));
    final repository = createRepository(adapter);

    await expectLater(
      repository.confirmPasswordReset(
        token: token,
        newPassword: 'Mealio-new-password-123',
      ),
      throwsA(
        isA<AuthFailure>()
            .having(
              (failure) => failure.type,
              'type',
              AuthFailureType.unexpected,
            )
            .having(
              (failure) => failure.toString(),
              'safe string',
              isNot(contains(token)),
            ),
      ),
    );
  });
}

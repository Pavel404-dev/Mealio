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

  test(
    'password reset OTP request accepts generic 202 and normalizes email',
    () async {
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 202,
            body: {
              'message':
                  'If an account with that email exists, a password reset code has been sent.',
            },
          ),
        );
      final repository = createRepository(adapter);

      await repository.requestPasswordResetOtp(email: '  PAVEL@EXAMPLE.COM  ');

      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.single.path, '/auth/password-reset/otp/request');
      expect(adapter.requests.single.data, {'email': 'pavel@example.com'});
    },
  );

  test(
    'password reset OTP request maps backend and rate-limit failures',
    () async {
      const email = 'private-reset-otp@example.com';
      final backendAdapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 503,
            body: {'detail': 'sensitive backend detail'},
          ),
        );
      final rateLimitAdapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse(
            statusCode: 429,
            body: {'detail': 'sensitive rate limit detail'},
          ),
        );

      for (final entry in [
        (
          createRepository(backendAdapter),
          AuthFailureType.passwordResetOtpRequest,
        ),
        (createRepository(rateLimitAdapter), AuthFailureType.rateLimited),
      ]) {
        try {
          await entry.$1.requestPasswordResetOtp(email: email);
          fail('Expected AuthFailure');
        } on AuthFailure catch (failure) {
          expect(failure.type, entry.$2);
          expect(failure.message, isNot(contains(email)));
          expect(failure.message, isNot(contains('sensitive')));
          expect(failure.toString(), isNot(contains(email)));
        }
      }
    },
  );

  test('password reset OTP request maps transport failure safely', () async {
    const email = 'private-network-reset-otp@example.com';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    try {
      await repository.requestPasswordResetOtp(email: email);
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.connection);
      expect(failure.message, isNot(contains(email)));
      expect(failure.toString(), isNot(contains(email)));
    }
  });

  test('password reset OTP confirm preserves code and password', () async {
    const code = '001234';
    const password = '  Mealio-new-password  ';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 204, body: null));
    final repository = createRepository(adapter);

    await repository.confirmPasswordResetOtp(
      email: '  PAVEL@EXAMPLE.COM  ',
      code: code,
      newPassword: password,
    );

    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.path, '/auth/password-reset/otp/confirm');
    expect(adapter.requests.single.data, {
      'email': 'pavel@example.com',
      'code': code,
      'new_password': password,
    });
  });

  test('password reset OTP confirm maps 400 without leaking secrets', () async {
    const email = 'private-confirm-reset-otp@example.com';
    const code = '654321';
    const password = 'Private-password-654321';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 400,
          body: {'detail': 'Invalid or expired password reset code.'},
        ),
      );
    final repository = createRepository(adapter);

    try {
      await repository.confirmPasswordResetOtp(
        email: email,
        code: code,
        newPassword: password,
      );
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.passwordResetOtpInvalid);
      for (final secret in [email, code, password]) {
        expect(failure.message, isNot(contains(secret)));
        expect(failure.toString(), isNot(contains(secret)));
      }
    }
  });

  test('password reset OTP confirm maps 422 and 429 safely', () async {
    const email = 'private-validation-reset-otp@example.com';
    const code = '123456';
    const password = 'Private-password-123456';

    for (final entry in [
      (422, AuthFailureType.passwordResetOtpValidation),
      (429, AuthFailureType.rateLimited),
    ]) {
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          FakeHttpResponse(
            statusCode: entry.$1,
            body: const {'detail': 'sensitive backend detail'},
          ),
        );
      final repository = createRepository(adapter);

      try {
        await repository.confirmPasswordResetOtp(
          email: email,
          code: code,
          newPassword: password,
        );
        fail('Expected AuthFailure');
      } on AuthFailure catch (failure) {
        expect(failure.type, entry.$2);
        for (final secret in [email, code, password, 'sensitive']) {
          expect(failure.message, isNot(contains(secret)));
          expect(failure.toString(), isNot(contains(secret)));
        }
      }
    }
  });

  test(
    'password reset OTP confirm maps transport and unexpected success safely',
    () async {
      const email = 'private-unexpected-reset-otp@example.com';
      const code = '987654';
      const password = 'Private-password-987654';
      final transportAdapter = FakeHttpClientAdapter()
        ..enqueue(
          const FakeHttpResponse.error(DioExceptionType.connectionError),
        );
      final unexpectedAdapter = FakeHttpClientAdapter()
        ..enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

      for (final entry in [
        (createRepository(transportAdapter), AuthFailureType.connection),
        (createRepository(unexpectedAdapter), AuthFailureType.unexpected),
      ]) {
        try {
          await entry.$1.confirmPasswordResetOtp(
            email: email,
            code: code,
            newPassword: password,
          );
          fail('Expected AuthFailure');
        } on AuthFailure catch (failure) {
          expect(failure.type, entry.$2);
          for (final secret in [email, code, password]) {
            expect(failure.message, isNot(contains(secret)));
            expect(failure.toString(), isNot(contains(secret)));
          }
        }
      }
    },
  );
}

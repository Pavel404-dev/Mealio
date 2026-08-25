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

  test('request email verification accepts generic 202 response', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 202,
          body: {
            'message':
                'If verification is needed for that email, verification instructions have been sent.',
          },
        ),
      );
    final repository = createRepository(adapter);

    await repository.requestEmailVerification(email: '  PAVEL@EXAMPLE.COM  ');

    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.path, '/auth/email-verification/request');
    expect(adapter.requests.single.data, {'email': 'pavel@example.com'});
  });

  test('request email verification maps backend failure safely', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 503,
          body: {'detail': 'temporarily unavailable'},
        ),
      );
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestEmailVerification(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.emailVerificationRequest,
        ),
      ),
    );
  });

  test('request email verification maps transport failure', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestEmailVerification(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.connection,
        ),
      ),
    );
  });

  test('confirm email verification accepts 204 response', () async {
    const token = 'opaque-verification-token';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 204, body: null));
    final repository = createRepository(adapter);

    await repository.confirmEmailVerification(token: token);

    expect(adapter.requests, hasLength(1));
    expect(adapter.requests.single.path, '/auth/email-verification/confirm');
    expect(adapter.requests.single.data, {'token': token});
  });

  test('confirm maps generic 400 without exposing raw token', () async {
    const token = 'secret-verification-token-that-must-not-leak';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 400,
          body: {'detail': 'Invalid or expired email verification token.'},
        ),
      );
    final repository = createRepository(adapter);

    try {
      await repository.confirmEmailVerification(token: token);
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.emailVerificationInvalid);
      expect(failure.message, isNot(contains(token)));
      expect(failure.toString(), isNot(contains(token)));
    }
  });

  test('confirm maps transport failure without exposing raw token', () async {
    const token = 'network-secret-verification-token';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    try {
      await repository.confirmEmailVerification(token: token);
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.connection);
      expect(failure.message, isNot(contains(token)));
      expect(failure.toString(), isNot(contains(token)));
    }
  });

  test('unexpected successful confirm status maps to safe failure', () async {
    const token = 'unexpected-status-token';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: {}));
    final repository = createRepository(adapter);

    await expectLater(
      repository.confirmEmailVerification(token: token),
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

  test('OTP request normalizes email and accepts generic 202', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 202,
          body: {
            'message':
                'If verification is needed for that email, a verification code has been sent.',
          },
        ),
      );
    final repository = createRepository(adapter);

    await repository.requestEmailVerificationOtp(
      email: '  PAVEL@EXAMPLE.COM  ',
    );

    expect(adapter.requests, hasLength(1));
    expect(
      adapter.requests.single.path,
      '/auth/email-verification/otp/request',
    );
    expect(adapter.requests.single.data, {'email': 'pavel@example.com'});
  });

  test('OTP request maps backend failure safely', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 503,
          body: {'detail': 'internal delivery state'},
        ),
      );
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestEmailVerificationOtp(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.emailVerificationOtpRequest,
        ),
      ),
    );
  });

  test('OTP request maps transport failure', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestEmailVerificationOtp(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.connection,
        ),
      ),
    );
  });

  test('OTP request maps 429 to generic rate-limit failure', () async {
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 429,
          body: {'detail': 'Too many requests.'},
        ),
      );
    final repository = createRepository(adapter);

    await expectLater(
      repository.requestEmailVerificationOtp(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.rateLimited,
        ),
      ),
    );
  });

  test('OTP confirm preserves leading zeroes and accepts 204', () async {
    const code = '001234';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 204, body: null));
    final repository = createRepository(adapter);

    await repository.confirmEmailVerificationOtp(
      email: '  PAVEL@EXAMPLE.COM  ',
      code: code,
    );

    expect(adapter.requests, hasLength(1));
    expect(
      adapter.requests.single.path,
      '/auth/email-verification/otp/confirm',
    );
    expect(adapter.requests.single.data, {
      'email': 'pavel@example.com',
      'code': code,
    });
    final requestData = adapter.requests.single.data as Map<String, dynamic>;
    expect(requestData['code'], isA<String>());
  });

  for (final statusCode in const [400, 422]) {
    test('OTP confirm maps $statusCode without exposing raw code', () async {
      const code = '009876';
      final adapter = FakeHttpClientAdapter()
        ..enqueue(
          FakeHttpResponse(
            statusCode: statusCode,
            body: const {
              'detail': 'Invalid or expired email verification code.',
            },
          ),
        );
      final repository = createRepository(adapter);

      try {
        await repository.confirmEmailVerificationOtp(
          email: 'pavel@example.com',
          code: code,
        );
        fail('Expected AuthFailure');
      } on AuthFailure catch (failure) {
        expect(failure.type, AuthFailureType.emailVerificationOtpInvalid);
        expect(failure.message, isNot(contains(code)));
        expect(failure.toString(), isNot(contains(code)));
      }
    });
  }

  test('OTP confirm maps 429 without exposing raw code', () async {
    const code = '001111';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(
        const FakeHttpResponse(
          statusCode: 429,
          body: {'detail': 'Too many requests.'},
        ),
      );
    final repository = createRepository(adapter);

    try {
      await repository.confirmEmailVerificationOtp(
        email: 'pavel@example.com',
        code: code,
      );
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.rateLimited);
      expect(failure.message, isNot(contains(code)));
      expect(failure.toString(), isNot(contains(code)));
    }
  });

  test('OTP confirm transport failure does not expose raw code', () async {
    const code = '004242';
    final adapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse.error(DioExceptionType.connectionError));
    final repository = createRepository(adapter);

    try {
      await repository.confirmEmailVerificationOtp(
        email: 'pavel@example.com',
        code: code,
      );
      fail('Expected AuthFailure');
    } on AuthFailure catch (failure) {
      expect(failure.type, AuthFailureType.connection);
      expect(failure.message, isNot(contains(code)));
      expect(failure.toString(), isNot(contains(code)));
    }
  });

  test('unexpected successful OTP statuses map to safe failures', () async {
    const code = '002222';
    final requestAdapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: {}));
    final confirmAdapter = FakeHttpClientAdapter()
      ..enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await expectLater(
      createRepository(
        requestAdapter,
      ).requestEmailVerificationOtp(email: 'pavel@example.com'),
      throwsA(
        isA<AuthFailure>().having(
          (failure) => failure.type,
          'type',
          AuthFailureType.unexpected,
        ),
      ),
    );

    await expectLater(
      createRepository(
        confirmAdapter,
      ).confirmEmailVerificationOtp(email: 'pavel@example.com', code: code),
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
              isNot(contains(code)),
            ),
      ),
    );
  });
}

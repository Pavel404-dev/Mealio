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
}

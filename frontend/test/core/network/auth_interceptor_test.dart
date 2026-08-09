import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/network/auth_interceptor.dart';

import '../../helpers/auth_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;

  setUp(() {
    adapter = FakeHttpClientAdapter();
    storage = FakeSecureStorageService();
  });

  test('stored token adds bearer Authorization header', () async {
    storage = FakeSecureStorageService(token: 'stored-token');
    final dio = createFakeDio(adapter)
      ..interceptors.add(AuthInterceptor(storage));

    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      adapter.requests.single.headers['Authorization'],
      'Bearer stored-token',
    );
  });

  test('missing token does not add Authorization header', () async {
    final dio = createFakeDio(adapter)
      ..interceptors.add(AuthInterceptor(storage));

    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      adapter.requests.single.headers.containsKey('Authorization'),
      isFalse,
    );
  });

  test('empty token does not add Authorization header', () async {
    storage = FakeSecureStorageService(token: '   ');
    final dio = createFakeDio(adapter)
      ..interceptors.add(AuthInterceptor(storage));

    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    await dio.get<Object?>('/auth/me');

    expect(
      adapter.requests.single.headers.containsKey('Authorization'),
      isFalse,
    );
  });

  test('token reading is awaited asynchronously', () async {
    final readCompleter = Completer<String?>();
    storage.pendingRead = readCompleter;

    final dio = createFakeDio(adapter)
      ..interceptors.add(AuthInterceptor(storage));

    adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: {}));

    final requestFuture = dio.get<Object?>('/auth/me');

    expect(adapter.requests, isEmpty);

    readCompleter.complete('async-token');
    await requestFuture;

    expect(storage.readCount, 1);
    expect(
      adapter.requests.single.headers['Authorization'],
      'Bearer async-token',
    );
  });

  test('login request never requires or attaches stored token', () async {
    storage = FakeSecureStorageService(token: 'stale-token');
    final dio = createFakeDio(adapter)
      ..interceptors.add(AuthInterceptor(storage));

    adapter.enqueue(
      const FakeHttpResponse(
        statusCode: 200,
        body: {'access_token': 'new-token', 'token_type': 'bearer'},
      ),
    );

    await dio.post<Object?>(
      '/auth/login',
      data: {'email': 'pavel@example.com', 'password': 'test-password'},
    );

    expect(storage.readCount, 0);
    expect(
      adapter.requests.single.headers.containsKey('Authorization'),
      isFalse,
    );
  });
}

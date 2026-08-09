import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';

final testAuthUser = AuthUser(
  id: '7c59f60a-8428-4bce-a2bd-bfe7dd10b3af',
  email: 'pavel@example.com',
  fullName: 'Pavel Potapenko',
  createdAt: DateTime.parse('2026-07-20T10:00:00Z'),
  updatedAt: DateTime.parse('2026-07-20T10:00:00Z'),
);

class FakeSecureStorageService extends SecureStorageService {
  FakeSecureStorageService({this._token}) : super(const FlutterSecureStorage());

  String? _token;
  Completer<String?>? pendingRead;

  int readCount = 0;
  int writeCount = 0;
  int deleteCount = 0;
  String? lastWrittenToken;

  String? get token => _token;

  @override
  Future<String?> readAccessToken() {
    readCount++;
    final completer = pendingRead;

    if (completer != null) {
      return completer.future;
    }

    return Future.value(_token);
  }

  @override
  Future<void> writeAccessToken(String token) async {
    writeCount++;
    lastWrittenToken = token;
    _token = token;
  }

  @override
  Future<void> deleteAccessToken() async {
    deleteCount++;
    _token = null;
  }
}

class FakeHttpResponse {
  const FakeHttpResponse({required this.statusCode, required this.body})
    : errorType = null;

  const FakeHttpResponse.error(this.errorType) : statusCode = 0, body = null;

  final int statusCode;
  final Object? body;
  final DioExceptionType? errorType;
}

class FakeHttpClientAdapter implements HttpClientAdapter {
  final Queue<FakeHttpResponse> _responses = Queue<FakeHttpResponse>();
  final List<RequestOptions> requests = <RequestOptions>[];

  void enqueue(FakeHttpResponse response) {
    _responses.add(response);
  }

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requests.add(options);

    if (_responses.isEmpty) {
      throw StateError('No fake HTTP response queued');
    }

    final response = _responses.removeFirst();

    if (response.errorType != null) {
      throw DioException(
        requestOptions: options,
        type: response.errorType!,
        error: 'Fake transport failure',
      );
    }

    return ResponseBody.fromString(
      jsonEncode(response.body),
      response.statusCode,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Dio createFakeDio(FakeHttpClientAdapter adapter) {
  final dio = Dio(
    BaseOptions(
      baseUrl: 'http://test.local/api/v1',
      responseType: ResponseType.json,
      headers: const {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
    ),
  );

  dio.httpClientAdapter = adapter;
  return dio;
}

class FakeAuthRepository extends AuthRepository {
  FakeAuthRepository({
    this.restoreHandler,
    this.loginHandler,
    this.logoutHandler,
  }) : super(apiClient: ApiClient(Dio()), storage: FakeSecureStorageService());

  Future<AuthUser?> Function()? restoreHandler;
  Future<AuthUser> Function({required String email, required String password})?
  loginHandler;
  Future<void> Function()? logoutHandler;

  int restoreCalls = 0;
  int loginCalls = 0;
  int logoutCalls = 0;
  String? lastLoginEmail;

  @override
  Future<AuthUser?> restoreSession() {
    restoreCalls++;
    return restoreHandler?.call() ?? Future<AuthUser?>.value(null);
  }

  @override
  Future<AuthUser> login({required String email, required String password}) {
    loginCalls++;
    lastLoginEmail = email;

    final handler = loginHandler;

    if (handler == null) {
      return Future<AuthUser>.value(testAuthUser);
    }

    return handler(email: email, password: password);
  }

  @override
  Future<void> logout() {
    logoutCalls++;
    return logoutHandler?.call() ?? Future<void>.value();
  }
}

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
  factory FakeSecureStorageService({
    String? token,
    String? accessToken,
    String? refreshToken,
    bool failAccessWrite = false,
    bool failRefreshWrite = false,
    bool failAccessDelete = false,
    bool failRefreshDelete = false,
  }) {
    return FakeSecureStorageService._(
      accessToken ?? token,
      refreshToken,
      failAccessWrite,
      failRefreshWrite,
      failAccessDelete,
      failRefreshDelete,
    );
  }

  FakeSecureStorageService._(
    this._accessToken,
    this._refreshToken,
    this.failAccessWrite,
    this.failRefreshWrite,
    this.failAccessDelete,
    this.failRefreshDelete,
  ) : super(const FlutterSecureStorage());

  String? _accessToken;
  String? _refreshToken;

  bool failAccessWrite;
  bool failRefreshWrite;
  bool failAccessDelete;
  bool failRefreshDelete;

  Completer<String?>? pendingRead;
  Completer<String?>? pendingRefreshRead;
  Completer<void>? accessWriteStarted;
  Completer<void>? pendingAccessWrite;

  int readCount = 0;
  int writeCount = 0;
  int deleteCount = 0;
  int refreshReadCount = 0;
  int refreshWriteCount = 0;
  int refreshDeleteCount = 0;
  String? lastWrittenToken;
  String? lastWrittenRefreshToken;

  String? get token => _accessToken;
  String? get accessToken => _accessToken;
  String? get refreshToken => _refreshToken;

  @override
  Future<String?> readAccessToken() {
    readCount++;
    final completer = pendingRead;

    if (completer != null) {
      return completer.future;
    }

    return Future.value(_accessToken);
  }

  @override
  Future<void> writeAccessToken(String token) async {
    writeCount++;
    lastWrittenToken = token;

    if (failAccessWrite) {
      throw StateError('Fake access-token write failure');
    }

    final started = accessWriteStarted;
    if (started != null && !started.isCompleted) {
      started.complete();
    }

    final pendingWrite = pendingAccessWrite;
    if (pendingWrite != null) {
      await pendingWrite.future;
    }

    _accessToken = token;
  }

  @override
  Future<void> deleteAccessToken() async {
    deleteCount++;

    if (failAccessDelete) {
      throw StateError('Fake access-token delete failure');
    }

    _accessToken = null;
  }

  @override
  Future<String?> readRefreshToken() {
    refreshReadCount++;
    final completer = pendingRefreshRead;

    if (completer != null) {
      return completer.future;
    }

    return Future.value(_refreshToken);
  }

  @override
  Future<void> writeRefreshToken(String token) async {
    refreshWriteCount++;
    lastWrittenRefreshToken = token;

    if (failRefreshWrite) {
      throw StateError('Fake refresh-token write failure');
    }

    _refreshToken = token;
  }

  @override
  Future<void> deleteRefreshToken() async {
    refreshDeleteCount++;

    if (failRefreshDelete) {
      throw StateError('Fake refresh-token delete failure');
    }

    _refreshToken = null;
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

typedef FakeHttpResponseHandler =
    FutureOr<FakeHttpResponse> Function(RequestOptions options);

class FakeHttpClientAdapter implements HttpClientAdapter {
  final Queue<FakeHttpResponse> _responses = Queue<FakeHttpResponse>();
  final List<RequestOptions> requests = <RequestOptions>[];

  FakeHttpResponseHandler? responseHandler;

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

    final FakeHttpResponse response;
    final handler = responseHandler;

    if (handler != null) {
      response = await handler(options);
    } else {
      if (_responses.isEmpty) {
        throw StateError('No fake HTTP response queued');
      }

      response = _responses.removeFirst();
    }

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
    this.currentUserHandler,
    this.loginHandler,
    this.registerHandler,
    this.requestEmailVerificationHandler,
    this.confirmEmailVerificationHandler,
    this.requestPasswordResetHandler,
    this.confirmPasswordResetHandler,
    this.logoutHandler,
  }) : super(apiClient: ApiClient(Dio()), storage: FakeSecureStorageService());

  Future<AuthUser?> Function()? restoreHandler;
  Future<AuthUser> Function()? currentUserHandler;
  Future<AuthUser> Function({required String email, required String password})?
  loginHandler;
  Future<AuthUser> Function({
    required String email,
    required String password,
    String? fullName,
  })?
  registerHandler;
  Future<void> Function({required String email})?
  requestEmailVerificationHandler;
  Future<void> Function({required String token})?
  confirmEmailVerificationHandler;
  Future<void> Function({required String email})? requestPasswordResetHandler;
  Future<void> Function({required String token, required String newPassword})?
  confirmPasswordResetHandler;
  Future<void> Function()? logoutHandler;

  int restoreCalls = 0;
  int currentUserCalls = 0;
  int loginCalls = 0;
  int registerCalls = 0;
  int requestEmailVerificationCalls = 0;
  int confirmEmailVerificationCalls = 0;
  int requestPasswordResetCalls = 0;
  int confirmPasswordResetCalls = 0;
  int logoutCalls = 0;
  String? lastLoginEmail;
  String? lastRegisterEmail;
  String? lastRegisterFullName;
  String? lastVerificationRequestEmail;
  String? lastVerificationToken;
  String? lastPasswordResetRequestEmail;
  String? lastPasswordResetToken;
  String? lastPasswordResetPassword;

  @override
  Future<AuthUser?> restoreSession() {
    restoreCalls++;
    return restoreHandler?.call() ?? Future<AuthUser?>.value(null);
  }

  @override
  Future<AuthUser> getCurrentUser() {
    currentUserCalls++;
    return currentUserHandler?.call() ?? Future<AuthUser>.value(testAuthUser);
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
  Future<AuthUser> register({
    required String email,
    required String password,
    String? fullName,
  }) {
    registerCalls++;
    lastRegisterEmail = email;
    lastRegisterFullName = fullName;

    final handler = registerHandler;

    if (handler == null) {
      return Future<AuthUser>.value(testAuthUser);
    }

    return handler(email: email, password: password, fullName: fullName);
  }

  @override
  Future<void> requestEmailVerification({required String email}) {
    requestEmailVerificationCalls++;
    lastVerificationRequestEmail = email;
    return requestEmailVerificationHandler?.call(email: email) ??
        Future<void>.value();
  }

  @override
  Future<void> confirmEmailVerification({required String token}) {
    confirmEmailVerificationCalls++;
    lastVerificationToken = token;
    return confirmEmailVerificationHandler?.call(token: token) ??
        Future<void>.value();
  }

  @override
  Future<void> requestPasswordReset({required String email}) {
    requestPasswordResetCalls++;
    lastPasswordResetRequestEmail = email;
    return requestPasswordResetHandler?.call(email: email) ??
        Future<void>.value();
  }

  @override
  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  }) {
    confirmPasswordResetCalls++;
    lastPasswordResetToken = token;
    lastPasswordResetPassword = newPassword;
    return confirmPasswordResetHandler?.call(
          token: token,
          newPassword: newPassword,
        ) ??
        Future<void>.value();
  }

  @override
  Future<void> logout() {
    logoutCalls++;
    return logoutHandler?.call() ?? Future<void>.value();
  }
}

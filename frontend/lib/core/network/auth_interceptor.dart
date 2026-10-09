import 'package:dio/dio.dart';

import '../storage/secure_storage_provider.dart';
import 'session_request.dart';
import 'token_refresh_coordinator.dart';

class AuthInterceptor extends Interceptor {
  factory AuthInterceptor({
    required Dio dio,
    required SecureStorageService storage,
    required TokenRefreshCoordinator refreshCoordinator,
  }) {
    dio.httpClientAdapter = SessionHttpClientAdapter(
      dio.httpClientAdapter,
      storage,
    );
    return AuthInterceptor._(dio, storage, refreshCoordinator);
  }

  AuthInterceptor._(this._dio, this._storage, this._refreshCoordinator);

  static const Set<String> _publicAuthPaths = {
    '/auth/login',
    '/auth/register',
    '/auth/refresh',
    '/auth/logout',
    '/auth/email-verification/request',
    '/auth/email-verification/confirm',
    '/auth/email-verification/otp/request',
    '/auth/email-verification/otp/confirm',
    '/auth/password-reset/request',
    '/auth/password-reset/confirm',
    '/auth/password-reset/otp/request',
    '/auth/password-reset/otp/confirm',
  };
  static const String _authRetriedKey = 'mealio_auth_retried';
  static const String _authGenerationKey = 'mealio_auth_generation';

  final Dio _dio;
  final SecureStorageService _storage;
  final TokenRefreshCoordinator _refreshCoordinator;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (_isPublicAuthRequest(options)) {
      options.extra.remove(sessionLifetimeKey);
      handler.next(options);
      return;
    }

    options.extra.putIfAbsent(
      sessionLifetimeKey,
      () => _storage.sessionLifetime,
    );
    final lifetime = options.extra[sessionLifetimeKey] as int;
    options.extra.putIfAbsent(
      _authGenerationKey,
      () => _storage.tokenPairRevision,
    );

    try {
      final token = (await _storage.readSessionAccessToken(lifetime))?.trim();
      _storage.checkSession(lifetime);

      if (token != null &&
          token.isNotEmpty &&
          !options.headers.containsKey('Authorization')) {
        options.headers['Authorization'] = 'Bearer $token';
      }

      handler.next(options);
    } on SessionSuperseded {
      handler.reject(supersededRequest(options));
    } catch (error, stackTrace) {
      handler.reject(
        DioException(
          requestOptions: options,
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    final lifetime = response.requestOptions.extra[sessionLifetimeKey];
    if (lifetime is int && !_storage.ownsSession(lifetime)) {
      handler.reject(supersededRequest(response.requestOptions));
      return;
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    final requestOptions = err.requestOptions;

    if (err.response?.statusCode != 401 ||
        _isPublicAuthRequest(requestOptions)) {
      handler.next(err);
      return;
    }

    if (requestOptions.extra[_authRetriedKey] == true) {
      handler.next(err);
      return;
    }

    final lifetime = requestOptions.extra[sessionLifetimeKey];
    if (lifetime is! int || !_storage.ownsSession(lifetime)) {
      handler.reject(supersededRequest(requestOptions));
      return;
    }

    final failedAccessToken = _extractBearerToken(
      requestOptions.headers['Authorization'],
    );

    final String? currentAccessToken;
    try {
      currentAccessToken = (await _storage.readSessionAccessToken(
        lifetime,
      ))?.trim();
      _storage.checkSession(lifetime);
    } on SessionSuperseded {
      handler.reject(supersededRequest(requestOptions));
      return;
    } catch (storageError, stackTrace) {
      handler.reject(
        DioException(
          requestOptions: requestOptions,
          error: storageError,
          stackTrace: stackTrace,
        ),
      );
      return;
    }

    if (failedAccessToken != null &&
        (currentAccessToken == null || currentAccessToken.isEmpty)) {
      handler.next(err);
      return;
    }

    final failedGeneration = requestOptions.extra[_authGenerationKey];
    if (failedGeneration is int &&
        failedGeneration < _storage.tokenPairRevision &&
        currentAccessToken != null &&
        currentAccessToken.isNotEmpty) {
      await _retryWithAccessToken(err, handler, currentAccessToken);
      return;
    }

    if (failedAccessToken != null &&
        currentAccessToken != null &&
        currentAccessToken.isNotEmpty &&
        failedAccessToken != currentAccessToken) {
      await _retryWithAccessToken(err, handler, currentAccessToken);
      return;
    }

    try {
      final tokenPair = await _refreshCoordinator.refreshTokens(
        sessionLifetime: lifetime,
      );
      await _retryWithAccessToken(err, handler, tokenPair.accessToken);
    } on TokenRefreshFailure catch (failure) {
      switch (failure.type) {
        case TokenRefreshFailureType.superseded:
          handler.reject(supersededRequest(requestOptions));
          return;
        case TokenRefreshFailureType.invalidSession:
          handler.next(err);
          return;
        case TokenRefreshFailureType.transient:
          handler.reject(
            _asOriginalRequestFailure(failure.cause!, requestOptions),
          );
          return;
      }
    }
  }

  Future<void> _retryWithAccessToken(
    DioException originalError,
    ErrorInterceptorHandler handler,
    String accessToken,
  ) async {
    final originalRequest = originalError.requestOptions;
    if (!_storage.ownsSession(
      originalRequest.extra[sessionLifetimeKey] as int,
    )) {
      handler.reject(supersededRequest(originalRequest));
      return;
    }
    final headers = Map<String, dynamic>.from(originalRequest.headers)
      ..['Authorization'] = 'Bearer $accessToken';
    final extra = Map<String, dynamic>.from(originalRequest.extra)
      ..[_authRetriedKey] = true;

    final retryRequest = originalRequest.copyWith(
      headers: headers,
      extra: extra,
    );

    try {
      final response = await _dio.fetch<Object?>(retryRequest);
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.reject(retryError);
    }
  }

  DioException _asOriginalRequestFailure(
    DioException refreshError,
    RequestOptions originalRequest,
  ) {
    final refreshResponse = refreshError.response;
    final response = refreshResponse == null
        ? null
        : Response<Object?>(
            requestOptions: originalRequest,
            statusCode: refreshResponse.statusCode,
            statusMessage: refreshResponse.statusMessage,
          );

    return DioException(
      requestOptions: originalRequest,
      response: response,
      type: refreshError.type,
      error: refreshError.error,
      stackTrace: refreshError.stackTrace,
    );
  }

  String? _extractBearerToken(Object? authorizationHeader) {
    if (authorizationHeader is! String) {
      return null;
    }

    const prefix = 'Bearer ';
    if (!authorizationHeader.startsWith(prefix)) {
      return null;
    }

    final token = authorizationHeader.substring(prefix.length).trim();
    return token.isEmpty ? null : token;
  }

  bool _isPublicAuthRequest(RequestOptions options) {
    final path = options.uri.path;
    return _publicAuthPaths.any(path.endsWith);
  }
}

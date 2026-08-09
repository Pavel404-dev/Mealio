import 'package:dio/dio.dart';

import '../storage/secure_storage_provider.dart';

class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._storage);

  static const Set<String> _publicAuthPaths = {'/auth/login', '/auth/register'};

  final SecureStorageService _storage;

  @override
  void onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (_publicAuthPaths.contains(options.path)) {
      handler.next(options);
      return;
    }

    try {
      final token = (await _storage.readAccessToken())?.trim();

      if (token != null &&
          token.isNotEmpty &&
          !options.headers.containsKey('Authorization')) {
        options.headers['Authorization'] = 'Bearer $token';
      }

      handler.next(options);
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
}

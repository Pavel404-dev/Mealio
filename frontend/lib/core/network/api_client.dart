import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../storage/secure_storage_provider.dart';
import 'dio_provider.dart';
import 'session_request.dart';

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(
    ref.watch(dioProvider),
    storage: ref.watch(secureStorageServiceProvider),
  );
});

class ApiClient {
  ApiClient(Dio dio, {SecureStorageService? storage}) : this._(dio, storage);

  ApiClient._(this._dio, this._storage);

  final Dio _dio;
  final SecureStorageService? _storage;

  Options? _options([int? lifetime]) {
    final captured = lifetime ?? _storage?.sessionLifetime;
    return captured == null
        ? null
        : Options(extra: {sessionLifetimeKey: captured});
  }

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    int? sessionLifetime,
  }) {
    return _dio.get<T>(
      path,
      queryParameters: queryParameters,
      options: _options(sessionLifetime),
    );
  }

  Future<Response<T>> post<T>(
    String path, {
    Object? data,
    Map<String, dynamic>? queryParameters,
  }) {
    return _dio.post<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: _options(),
    );
  }

  Future<Response<T>> patch<T>(String path, {Object? data}) {
    return _dio.patch<T>(path, data: data, options: _options());
  }

  Future<Response<T>> delete<T>(String path) {
    return _dio.delete<T>(path, options: _options());
  }
}

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../domain/auth_failure.dart';
import '../domain/auth_user.dart';

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(
    apiClient: ref.watch(apiClientProvider),
    storage: ref.watch(secureStorageServiceProvider),
  );
});

class AuthRepository {
  AuthRepository({required this._apiClient, required this._storage});

  final ApiClient _apiClient;
  final SecureStorageService _storage;

  Future<AuthUser> login({
    required String email,
    required String password,
  }) async {
    final token = await _requestAccessToken(email: email, password: password);

    try {
      await _storage.writeAccessToken(token);
    } catch (_) {
      throw AuthFailure.unexpected();
    }

    try {
      return await getCurrentUser();
    } catch (_) {
      await _deleteAccessTokenBestEffort();
      rethrow;
    }
  }

  Future<AuthUser> getCurrentUser() async {
    try {
      final response = await _apiClient.get<Object?>('/auth/me');
      return AuthUser.fromJson(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, isLoginRequest: false);
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<AuthUser?> restoreSession() async {
    final String? storedToken;

    try {
      storedToken = await _storage.readAccessToken();
    } catch (_) {
      throw AuthFailure.unexpected();
    }

    if (storedToken == null || storedToken.trim().isEmpty) {
      if (storedToken != null) {
        await _deleteAccessTokenBestEffort();
      }

      return null;
    }

    try {
      return await getCurrentUser();
    } on AuthFailure catch (failure) {
      if (failure.type == AuthFailureType.invalidSession) {
        await _deleteAccessTokenBestEffort();
        return null;
      }

      rethrow;
    }
  }

  Future<void> logout() async {
    try {
      await _storage.deleteAccessToken();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<String> _requestAccessToken({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/login',
        data: {'email': email.trim(), 'password': password},
      );

      return _parseAccessToken(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, isLoginRequest: true);
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  String _parseAccessToken(Object? data) {
    if (data is! Map<String, dynamic>) {
      throw const FormatException('Invalid login response');
    }

    final accessToken = data['access_token'];
    final tokenType = data['token_type'];

    if (accessToken is! String ||
        accessToken.trim().isEmpty ||
        tokenType != 'bearer') {
      throw const FormatException('Invalid login response');
    }

    return accessToken.trim();
  }

  AuthFailure _mapDioException(
    DioException error, {
    required bool isLoginRequest,
  }) {
    final statusCode = error.response?.statusCode;

    if (isLoginRequest && statusCode == 401) {
      return AuthFailure.invalidCredentials();
    }

    if (isLoginRequest && statusCode == 422) {
      return AuthFailure.validation();
    }

    if (!isLoginRequest && statusCode == 401) {
      return AuthFailure.invalidSession();
    }

    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
      case DioExceptionType.connectionError:
        return AuthFailure.connection();
      case DioExceptionType.badCertificate:
      case DioExceptionType.badResponse:
      case DioExceptionType.cancel:
      case DioExceptionType.unknown:
        return AuthFailure.unexpected();
    }
  }

  Future<void> _deleteAccessTokenBestEffort() async {
    try {
      await _storage.deleteAccessToken();
    } catch (_) {
      // Keep the original authentication failure as the visible error.
    }
  }
}

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/auth_token_pair.dart';
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
  AuthRepository({
    required ApiClient apiClient,
    required SecureStorageService storage,
  }) : this._(apiClient, storage);

  AuthRepository._(this._apiClient, this._storage);

  final ApiClient _apiClient;
  final SecureStorageService _storage;

  Future<AuthUser> register({
    required String email,
    required String password,
    String? fullName,
  }) async {
    final normalizedFullName = fullName?.trim();

    try {
      final response = await _apiClient.post<Object?>(
        '/auth/register',
        data: {
          'email': email.trim().toLowerCase(),
          'full_name': normalizedFullName == null || normalizedFullName.isEmpty
              ? null
              : normalizedFullName,
          'password': password,
        },
      );

      if (response.statusCode != 201) {
        throw const FormatException('Unexpected registration status code');
      }

      return AuthUser.fromJson(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, requestKind: _AuthRequestKind.registration);
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> requestEmailVerification({required String email}) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/email-verification/request',
        data: {'email': email.trim().toLowerCase()},
      );

      if (response.statusCode != 202) {
        throw const FormatException(
          'Unexpected email verification request status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.emailVerificationRequest,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> confirmEmailVerification({required String token}) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/email-verification/confirm',
        data: {'token': token},
      );

      if (response.statusCode != 204) {
        throw const FormatException(
          'Unexpected email verification confirmation status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.emailVerificationConfirm,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> requestEmailVerificationOtp({required String email}) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/email-verification/otp/request',
        data: {'email': email.trim().toLowerCase()},
      );

      if (response.statusCode != 202) {
        throw const FormatException(
          'Unexpected email verification OTP request status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.emailVerificationOtpRequest,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> confirmEmailVerificationOtp({
    required String email,
    required String code,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/email-verification/otp/confirm',
        data: {'email': email.trim().toLowerCase(), 'code': code},
      );

      if (response.statusCode != 204) {
        throw const FormatException(
          'Unexpected email verification OTP confirmation status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.emailVerificationOtpConfirm,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> requestPasswordReset({required String email}) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/password-reset/request',
        data: {'email': email.trim().toLowerCase()},
      );

      if (response.statusCode != 202) {
        throw const FormatException(
          'Unexpected password reset request status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.passwordResetRequest,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> confirmPasswordReset({
    required String token,
    required String newPassword,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/password-reset/confirm',
        data: {'token': token, 'new_password': newPassword},
      );

      if (response.statusCode != 204) {
        throw const FormatException(
          'Unexpected password reset confirmation status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.passwordResetConfirm,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> requestPasswordResetOtp({required String email}) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/password-reset/otp/request',
        data: {'email': email.trim().toLowerCase()},
      );

      if (response.statusCode != 202) {
        throw const FormatException(
          'Unexpected password reset OTP request status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.passwordResetOtpRequest,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<void> confirmPasswordResetOtp({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/password-reset/otp/confirm',
        data: {
          'email': email.trim().toLowerCase(),
          'code': code,
          'new_password': newPassword,
        },
      );

      if (response.statusCode != 204) {
        throw const FormatException(
          'Unexpected password reset OTP confirmation status code',
        );
      }
    } on DioException catch (error) {
      throw _mapDioException(
        error,
        requestKind: _AuthRequestKind.passwordResetOtpConfirm,
      );
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  int get sessionLifetime => _storage.sessionLifetime;

  Future<AuthUser> login({
    required String email,
    required String password,
  }) async {
    // End the previous lifetime synchronously, before login network I/O.
    final cleanup = _storage.deleteTokenPair();
    final lifetime = sessionLifetime;
    AuthTokenPair? pair;
    var saved = false;
    try {
      await cleanup;
      _storage.checkSession(lifetime);
      pair = await _requestTokenPair(email: email, password: password);
      saved = await _storage.writeTokenPairForSession(lifetime, pair);
      if (!saved) throw const SessionSuperseded();
      return await _getCurrentUser(lifetime);
    } catch (error) {
      final superseded = !_storage.ownsSession(lifetime);
      if (pair != null && !saved) await _revokePairBestEffort(pair);
      await _deleteTokenPairBestEffort(lifetime);
      if (superseded) throw const SessionSuperseded();
      if (error is AuthFailure) rethrow;
      throw AuthFailure.unexpected();
    }
  }

  Future<AuthUser> getCurrentUser() => _getCurrentUser(sessionLifetime);

  Future<AuthUser> _getCurrentUser(int lifetime) async {
    try {
      _storage.checkSession(lifetime);
      final response = await _apiClient.get<Object?>(
        '/auth/me',
        sessionLifetime: lifetime,
      );
      _storage.checkSession(lifetime);
      return AuthUser.fromJson(response.data);
    } on SessionSuperseded {
      rethrow;
    } on DioException catch (error) {
      if (error.error is SessionSuperseded ||
          (!_storage.ownsSession(lifetime) &&
              error.response?.statusCode != 401)) {
        throw const SessionSuperseded();
      }
      throw _mapDioException(error, requestKind: _AuthRequestKind.session);
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  Future<AuthUser?> restoreSession() async {
    final lifetime = sessionLifetime;
    final String? storedAccessToken;
    final String? storedRefreshToken;
    try {
      storedAccessToken = await _storage.readSessionAccessToken(lifetime);
      storedRefreshToken = await _storage.readSessionRefreshToken(lifetime);
      _storage.checkSession(lifetime);
    } on SessionSuperseded {
      rethrow;
    } catch (_) {
      throw AuthFailure.unexpected();
    }

    final accessToken = storedAccessToken?.trim();
    final refreshToken = storedRefreshToken?.trim();
    if (accessToken == null || accessToken.isEmpty) {
      if (storedAccessToken != null || storedRefreshToken != null) {
        await _deleteTokenPairBestEffort(lifetime);
      }
      return null;
    }
    if (storedRefreshToken != null &&
        (refreshToken == null || refreshToken.isEmpty)) {
      try {
        await _storage.deleteEmptyRefreshTokenForSession(lifetime);
      } catch (_) {
        // A valid legacy access token can still be checked by /auth/me.
      }
    }
    try {
      return await _getCurrentUser(lifetime);
    } on AuthFailure catch (failure) {
      if (failure.type == AuthFailureType.invalidSession) {
        await _deleteTokenPairBestEffort(lifetime);
        return null;
      }
      rethrow;
    }
  }

  Future<void> _revokePairBestEffort(AuthTokenPair pair) async {
    try {
      await _apiClient.post<Object?>(
        '/auth/logout',
        data: {'refresh_token': pair.refreshToken},
      );
    } catch (_) {
      // Only the orphan returned to this login operation is revoked.
    }
  }

  Future<void> logout() async {
    String? refreshToken;
    Object? cleanupError;

    try {
      refreshToken = await _storage.deleteTokenPairAndGetRefreshToken();
    } catch (error) {
      cleanupError = error;
    }

    if (refreshToken != null && refreshToken.isNotEmpty) {
      try {
        await _apiClient.post<Object?>(
          '/auth/logout',
          data: {'refresh_token': refreshToken},
        );
      } catch (_) {
        // Backend logout is best effort; local logout must still complete.
      }
    }

    if (cleanupError != null) {
      throw AuthFailure.unexpected();
    }
  }

  Future<AuthTokenPair> _requestTokenPair({
    required String email,
    required String password,
  }) async {
    try {
      final response = await _apiClient.post<Object?>(
        '/auth/login',
        data: {'email': email.trim(), 'password': password},
      );

      return AuthTokenPair.fromJson(response.data);
    } on DioException catch (error) {
      throw _mapDioException(error, requestKind: _AuthRequestKind.login);
    } on FormatException {
      throw AuthFailure.unexpected();
    } catch (_) {
      throw AuthFailure.unexpected();
    }
  }

  AuthFailure _mapDioException(
    DioException error, {
    required _AuthRequestKind requestKind,
  }) {
    final statusCode = error.response?.statusCode;

    if (requestKind == _AuthRequestKind.login) {
      if (statusCode == 401) {
        return AuthFailure.invalidCredentials();
      }

      if (statusCode == 422) {
        return AuthFailure.validation();
      }
    }

    if (requestKind == _AuthRequestKind.registration) {
      if (statusCode == 409) {
        return AuthFailure.duplicateEmail();
      }

      if (statusCode == 422) {
        return AuthFailure.registrationValidation();
      }
    }

    if (requestKind == _AuthRequestKind.emailVerificationRequest &&
        statusCode != null) {
      return AuthFailure.emailVerificationRequest();
    }

    if (requestKind == _AuthRequestKind.emailVerificationConfirm &&
        (statusCode == 400 || statusCode == 422)) {
      return AuthFailure.invalidEmailVerification();
    }

    if (requestKind == _AuthRequestKind.emailVerificationOtpRequest) {
      if (statusCode == 429) {
        return AuthFailure.rateLimited();
      }

      if (statusCode != null) {
        return AuthFailure.emailVerificationOtpRequest();
      }
    }

    if (requestKind == _AuthRequestKind.emailVerificationOtpConfirm) {
      if (statusCode == 429) {
        return AuthFailure.rateLimited();
      }

      if (statusCode == 400 || statusCode == 422) {
        return AuthFailure.invalidEmailVerificationOtp();
      }
    }

    if (requestKind == _AuthRequestKind.passwordResetRequest &&
        statusCode != null) {
      return AuthFailure.passwordResetRequest();
    }

    if ((requestKind == _AuthRequestKind.passwordResetConfirm ||
            requestKind == _AuthRequestKind.passwordResetOtpConfirm) &&
        statusCode == 400) {
      final data = error.response?.data;
      if (data is Map<String, dynamic> &&
          data['detail'] ==
              'New password must be different from the current password.') {
        return AuthFailure.passwordResetPasswordReuse();
      }
    }

    if (requestKind == _AuthRequestKind.passwordResetConfirm) {
      if (statusCode == 400) {
        return AuthFailure.invalidPasswordReset();
      }

      if (statusCode == 422) {
        return AuthFailure.passwordResetValidation();
      }
    }

    if (requestKind == _AuthRequestKind.passwordResetOtpRequest) {
      if (statusCode == 429) {
        return AuthFailure.rateLimited();
      }

      if (statusCode != null) {
        return AuthFailure.passwordResetOtpRequest();
      }
    }

    if (requestKind == _AuthRequestKind.passwordResetOtpConfirm) {
      if (statusCode == 429) {
        return AuthFailure.rateLimited();
      }

      if (statusCode == 400) {
        return AuthFailure.invalidPasswordResetOtp();
      }

      if (statusCode == 422) {
        return AuthFailure.passwordResetOtpValidation();
      }
    }

    if (requestKind == _AuthRequestKind.session && statusCode == 401) {
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

  Future<void> _deleteTokenPairBestEffort(int lifetime) async {
    try {
      await _storage.deleteTokenPairIfSessionMatches(lifetime);
    } catch (_) {
      // Keep the original authentication failure as the visible error.
    }
  }
}

enum _AuthRequestKind {
  login,
  registration,
  emailVerificationRequest,
  emailVerificationConfirm,
  emailVerificationOtpRequest,
  emailVerificationOtpConfirm,
  passwordResetRequest,
  passwordResetConfirm,
  passwordResetOtpRequest,
  passwordResetOtpConfirm,
  session,
}

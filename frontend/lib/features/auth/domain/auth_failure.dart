enum AuthFailureType {
  invalidCredentials,
  validation,
  duplicateEmail,
  registrationValidation,
  emailVerificationInvalid,
  emailVerificationRequest,
  emailVerificationOtpRequest,
  emailVerificationOtpInvalid,
  rateLimited,
  passwordResetRequest,
  passwordResetInvalid,
  passwordResetValidation,
  connection,
  invalidSession,
  unexpected,
}

class AuthFailure implements Exception {
  const AuthFailure({required this.type, required this.message});

  factory AuthFailure.invalidCredentials() {
    return const AuthFailure(
      type: AuthFailureType.invalidCredentials,
      message: 'Invalid email or password.',
    );
  }

  factory AuthFailure.validation() {
    return const AuthFailure(
      type: AuthFailureType.validation,
      message: 'Please check the entered email and password.',
    );
  }

  factory AuthFailure.duplicateEmail() {
    return const AuthFailure(
      type: AuthFailureType.duplicateEmail,
      message: 'An account with this email already exists.',
    );
  }

  factory AuthFailure.registrationValidation() {
    return const AuthFailure(
      type: AuthFailureType.registrationValidation,
      message: 'Please check the registration details.',
    );
  }

  factory AuthFailure.invalidEmailVerification() {
    return const AuthFailure(
      type: AuthFailureType.emailVerificationInvalid,
      message: 'This verification link is invalid or has expired.',
    );
  }

  factory AuthFailure.emailVerificationRequest() {
    return const AuthFailure(
      type: AuthFailureType.emailVerificationRequest,
      message: 'Unable to resend verification email. Please try again.',
    );
  }

  factory AuthFailure.emailVerificationOtpRequest() {
    return const AuthFailure(
      type: AuthFailureType.emailVerificationOtpRequest,
      message: 'Unable to request a verification code. Please try again.',
    );
  }

  factory AuthFailure.invalidEmailVerificationOtp() {
    return const AuthFailure(
      type: AuthFailureType.emailVerificationOtpInvalid,
      message: 'Invalid or expired verification code.',
    );
  }

  factory AuthFailure.rateLimited() {
    return const AuthFailure(
      type: AuthFailureType.rateLimited,
      message: 'Too many requests. Please try again later.',
    );
  }

  factory AuthFailure.passwordResetRequest() {
    return const AuthFailure(
      type: AuthFailureType.passwordResetRequest,
      message: 'Unable to send password reset instructions. Please try again.',
    );
  }

  factory AuthFailure.invalidPasswordReset() {
    return const AuthFailure(
      type: AuthFailureType.passwordResetInvalid,
      message: 'This password reset link is invalid or has expired.',
    );
  }

  factory AuthFailure.passwordResetValidation() {
    return const AuthFailure(
      type: AuthFailureType.passwordResetValidation,
      message: 'Please check the new password and try again.',
    );
  }

  factory AuthFailure.connection() {
    return const AuthFailure(
      type: AuthFailureType.connection,
      message: 'Unable to connect to the server. Please try again.',
    );
  }

  factory AuthFailure.invalidSession() {
    return const AuthFailure(
      type: AuthFailureType.invalidSession,
      message: 'Something went wrong. Please try again.',
    );
  }

  factory AuthFailure.unexpected() {
    return const AuthFailure(
      type: AuthFailureType.unexpected,
      message: 'Something went wrong. Please try again.',
    );
  }

  final AuthFailureType type;
  final String message;

  @override
  String toString() => 'AuthFailure($type)';
}

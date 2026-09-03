import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../data/auth_repository.dart';
import '../domain/auth_failure.dart';
import 'auth_controller.dart';

class PasswordResetOtpScreen extends ConsumerStatefulWidget {
  const PasswordResetOtpScreen({super.key, this.email});

  final String? email;

  @override
  ConsumerState<PasswordResetOtpScreen> createState() =>
      _PasswordResetOtpScreenState();
}

class _PasswordResetOtpScreenState
    extends ConsumerState<PasswordResetOtpScreen> {
  static const int _minimumPasswordLength = 15;
  static const int _maximumPasswordLength = 128;
  static final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
  static final RegExp _otpPattern = RegExp(r'^[0-9]{6}$');
  static const String _requestSuccessMessage =
      'If an account with that email exists, a password reset code has been sent.';

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _otpController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();
  final FocusNode _otpFocusNode = FocusNode();

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _isRequestingOtp = false;
  bool _isSubmitting = false;
  bool _isComplete = false;
  String? _requestMessage;
  AuthFailure? _requestFailure;
  AuthFailure? _confirmationFailure;

  String? get _normalizedEmail {
    final email = widget.email?.trim().toLowerCase();
    if (email == null || !_emailPattern.hasMatch(email)) {
      return null;
    }

    return email;
  }

  bool get _operationInProgress => _isRequestingOtp || _isSubmitting;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _normalizedEmail != null) {
        _otpFocusNode.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _otpController.clear();
    _passwordController.clear();
    _confirmPasswordController.clear();
    _otpController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _otpFocusNode.dispose();
    super.dispose();
  }

  String? _validateOtp(String? value) {
    if (value == null || !_otpPattern.hasMatch(value)) {
      return 'Enter the six-digit code from your email.';
    }

    return null;
  }

  String? _validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required.';
    }

    if (value.trim().isEmpty) {
      return 'Password cannot contain only whitespace.';
    }

    final length = value.runes.length;
    if (length < _minimumPasswordLength) {
      return 'Password must be at least 15 characters.';
    }

    if (length > _maximumPasswordLength) {
      return 'Password must be 128 characters or fewer.';
    }

    return null;
  }

  String? _validateConfirmPassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please confirm your password.';
    }

    if (value != _passwordController.text) {
      return 'Passwords do not match.';
    }

    return null;
  }

  Future<void> _requestOtp() async {
    final email = _normalizedEmail;
    if (email == null || _operationInProgress) {
      return;
    }

    setState(() {
      _isRequestingOtp = true;
      _requestMessage = null;
      _requestFailure = null;
      _confirmationFailure = null;
    });

    try {
      await ref
          .read(authRepositoryProvider)
          .requestPasswordResetOtp(email: email);

      if (!mounted) {
        return;
      }

      _otpController.clear();
      setState(() {
        _isRequestingOtp = false;
        _requestMessage = _requestSuccessMessage;
      });
      _otpFocusNode.requestFocus();
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRequestingOtp = false;
        _requestFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRequestingOtp = false;
        _requestFailure = AuthFailure.unexpected();
      });
    }
  }

  Future<void> _submit() async {
    final email = _normalizedEmail;
    if (email == null || _operationInProgress) {
      return;
    }

    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isSubmitting = true;
      _confirmationFailure = null;
    });

    try {
      await ref.read(authControllerProvider.future);

      if (!mounted) {
        return;
      }

      await ref
          .read(authRepositoryProvider)
          .confirmPasswordResetOtp(
            email: email,
            code: _otpController.text,
            newPassword: _passwordController.text,
          );

      if (!mounted) {
        return;
      }

      try {
        await ref.read(authControllerProvider.notifier).logout();
      } catch (_) {
        // logout() still transitions global auth state to unauthenticated.
      }

      if (!mounted) {
        return;
      }

      _otpController.clear();
      _passwordController.clear();
      _confirmPasswordController.clear();
      _otpFocusNode.unfocus();

      setState(() {
        _isSubmitting = false;
        _isComplete = true;
      });
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      if (failure.type == AuthFailureType.passwordResetOtpInvalid) {
        _otpController.clear();
        _otpFocusNode.requestFocus();
      }

      setState(() {
        _isSubmitting = false;
        _confirmationFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _confirmationFailure = AuthFailure.unexpected();
      });
    }
  }

  void _goBack() {
    if (_operationInProgress) {
      return;
    }

    if (context.canPop()) {
      context.pop();
      return;
    }

    context.go('/forgot-password');
  }

  @override
  Widget build(BuildContext context) {
    final email = _normalizedEmail;
    if (email == null) {
      return _buildUnavailable(context);
    }

    if (_isComplete) {
      return _buildSuccess(context);
    }

    return PopScope(
      canPop: !_operationInProgress,
      child: Scaffold(
        key: const Key('password-reset-otp-screen'),
        body: SafeArea(
          child: Form(
            key: _formKey,
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 560),
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(24, 20, 24, 32),
                  children: [
                    Align(
                      alignment: Alignment.centerLeft,
                      child: IconButton(
                        key: const Key('password-reset-otp-back-button'),
                        tooltip: 'Back',
                        onPressed: _operationInProgress ? null : _goBack,
                        icon: const Icon(Icons.arrow_back_rounded),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Container(
                        width: 64,
                        height: 64,
                        decoration: BoxDecoration(
                          color: AppColors.forest,
                          borderRadius: BorderRadius.circular(22),
                        ),
                        child: const Icon(
                          Icons.password_rounded,
                          color: Colors.white,
                          size: 32,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      'Reset with a code',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      'Enter the six-digit code from your email and choose a new password.',
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 24),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 18,
                        vertical: 16,
                      ),
                      decoration: BoxDecoration(
                        color: AppColors.cream,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Email address',
                            style: Theme.of(context).textTheme.labelLarge,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            email,
                            key: const Key('password-reset-otp-address'),
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 24),
                    TextFormField(
                      key: const Key('password-reset-otp-code-field'),
                      controller: _otpController,
                      focusNode: _otpFocusNode,
                      validator: _validateOtp,
                      enabled: !_operationInProgress,
                      keyboardType: TextInputType.number,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.oneTimeCode],
                      enableSuggestions: false,
                      autocorrect: false,
                      maxLength: 6,
                      inputFormatters: [
                        FilteringTextInputFormatter.allow(RegExp(r'[0-9]')),
                        LengthLimitingTextInputFormatter(6),
                      ],
                      onChanged: (_) {
                        setState(() {
                          _confirmationFailure = null;
                        });
                      },
                      decoration: const InputDecoration(
                        labelText: 'Six-digit reset code',
                        hintText: '000000',
                        prefixIcon: Icon(Icons.pin_outlined),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      key: const Key('password-reset-otp-password-field'),
                      controller: _passwordController,
                      validator: _validatePassword,
                      enabled: !_operationInProgress,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.newPassword],
                      decoration: InputDecoration(
                        labelText: 'New password',
                        helperText: 'Use 15–128 characters.',
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? 'Show password'
                              : 'Hide password',
                          onPressed: _operationInProgress
                              ? null
                              : () {
                                  setState(() {
                                    _obscurePassword = !_obscurePassword;
                                  });
                                },
                          icon: Icon(
                            _obscurePassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      key: const Key(
                        'password-reset-otp-confirm-password-field',
                      ),
                      controller: _confirmPasswordController,
                      validator: _validateConfirmPassword,
                      enabled: !_operationInProgress,
                      obscureText: _obscureConfirmPassword,
                      textInputAction: TextInputAction.done,
                      autofillHints: const [AutofillHints.newPassword],
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Confirm new password',
                        prefixIcon: const Icon(Icons.lock_reset_rounded),
                        suffixIcon: IconButton(
                          tooltip: _obscureConfirmPassword
                              ? 'Show password confirmation'
                              : 'Hide password confirmation',
                          onPressed: _operationInProgress
                              ? null
                              : () {
                                  setState(() {
                                    _obscureConfirmPassword =
                                        !_obscureConfirmPassword;
                                  });
                                },
                          icon: Icon(
                            _obscureConfirmPassword
                                ? Icons.visibility_outlined
                                : Icons.visibility_off_outlined,
                          ),
                        ),
                      ),
                    ),
                    if (_confirmationFailure != null) ...[
                      const SizedBox(height: 16),
                      _buildMessage(
                        context,
                        key: const Key('password-reset-otp-confirm-error'),
                        message: _confirmationFailure!.message,
                        isError: true,
                      ),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      key: const Key('password-reset-otp-submit-button'),
                      onPressed: _operationInProgress ? null : _submit,
                      child: _isSubmitting
                          ? const SizedBox(
                              key: Key('password-reset-otp-submit-loading'),
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Reset password'),
                    ),
                    const SizedBox(height: 12),
                    OutlinedButton.icon(
                      key: const Key('password-reset-otp-resend-button'),
                      onPressed: _operationInProgress ? null : _requestOtp,
                      icon: _isRequestingOtp
                          ? const SizedBox(
                              key: Key('password-reset-otp-resend-loading'),
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.mark_email_unread_outlined),
                      label: Text(
                        _isRequestingOtp ? 'Sending…' : 'Resend code',
                      ),
                    ),
                    if (_requestMessage != null) ...[
                      const SizedBox(height: 16),
                      _buildMessage(
                        context,
                        key: const Key('password-reset-otp-resend-success'),
                        message: _requestMessage!,
                        isError: false,
                      ),
                    ],
                    if (_requestFailure != null) ...[
                      const SizedBox(height: 16),
                      _buildMessage(
                        context,
                        key: const Key('password-reset-otp-resend-error'),
                        message: _requestFailure!.message,
                        isError: true,
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildUnavailable(BuildContext context) {
    return _buildShell(
      context,
      icon: Icons.lock_reset_rounded,
      title: 'Password reset code unavailable',
      subtitle: 'Request a new password reset code to continue.',
      children: [
        FilledButton(
          key: const Key('password-reset-otp-request-new-button'),
          onPressed: () => context.go('/forgot-password'),
          child: const Text('Request a new code'),
        ),
        const SizedBox(height: 12),
        TextButton(
          key: const Key('password-reset-otp-unavailable-login-button'),
          onPressed: () => context.go('/login'),
          child: const Text('Back to login'),
        ),
      ],
    );
  }

  Widget _buildSuccess(BuildContext context) {
    return _buildShell(
      context,
      icon: Icons.check_circle_outline_rounded,
      title: 'Password reset complete',
      subtitle:
          'Your password has been changed. Sign in again with your new password.',
      children: [
        FilledButton(
          key: const Key('password-reset-otp-success-login-button'),
          onPressed: () => context.go('/login'),
          child: const Text('Go to login'),
        ),
      ],
    );
  }

  Widget _buildMessage(
    BuildContext context, {
    required Key key,
    required String message,
    required bool isError,
  }) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      key: key,
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isError ? colorScheme.errorContainer : AppColors.cream,
        borderRadius: BorderRadius.circular(16),
        border: isError ? null : Border.all(color: AppColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            isError ? Icons.error_outline_rounded : Icons.info_outline_rounded,
            color: isError ? colorScheme.onErrorContainer : AppColors.forest,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: isError ? colorScheme.onErrorContainer : null,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildShell(
    BuildContext context, {
    required IconData icon,
    required String title,
    required String subtitle,
    required List<Widget> children,
  }) {
    return Scaffold(
      key: const Key('password-reset-otp-screen'),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 560),
            child: ListView(
              padding: const EdgeInsets.fromLTRB(24, 28, 24, 32),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: AppColors.forest,
                      borderRadius: BorderRadius.circular(22),
                    ),
                    child: Icon(icon, color: Colors.white, size: 32),
                  ),
                ),
                const SizedBox(height: 24),
                Text(title, style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 10),
                Text(subtitle, style: Theme.of(context).textTheme.bodyLarge),
                const SizedBox(height: 28),
                ...children,
              ],
            ),
          ),
        ),
      ),
    );
  }
}

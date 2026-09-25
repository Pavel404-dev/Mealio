import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/localization/l10n.dart';
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
  String get _requestSuccessMessage => context.l10n.resetCodeSent;

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
  bool _showRequestMessage = false;
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
      return context.l10n.otpInvalidInput;
    }

    return null;
  }

  String? _validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return context.l10n.passwordRequired;
    }

    if (value.trim().isEmpty) {
      return context.l10n.passwordWhitespace;
    }

    final length = value.runes.length;
    if (length < _minimumPasswordLength) {
      return context.l10n.passwordMinimum(_minimumPasswordLength);
    }

    if (length > _maximumPasswordLength) {
      return context.l10n.passwordMaximum(_maximumPasswordLength);
    }

    return null;
  }

  String? _validateConfirmPassword(String? value) {
    if (value == null || value.isEmpty) {
      return context.l10n.passwordConfirmRequired;
    }

    if (value != _passwordController.text) {
      return context.l10n.passwordMismatch;
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
      _showRequestMessage = false;
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
        _showRequestMessage = true;
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
          child: LocalizedForm(
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
                        tooltip: context.l10n.back,
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
                      context.l10n.resetWithCode,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      context.l10n.resetWithCodeDescription,
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
                            context.l10n.emailAddress,
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
                      decoration: InputDecoration(
                        labelText: context.l10n.resetCodeLabel,
                        hintText: context.l10n.otpHint,
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
                        labelText: context.l10n.newPassword,
                        helperText: context.l10n.passwordHint,
                        prefixIcon: const Icon(Icons.lock_outline_rounded),
                        suffixIcon: IconButton(
                          tooltip: _obscurePassword
                              ? context.l10n.showPassword
                              : context.l10n.hidePassword,
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
                        labelText: context.l10n.confirmNewPassword,
                        prefixIcon: const Icon(Icons.lock_reset_rounded),
                        suffixIcon: IconButton(
                          tooltip: _obscureConfirmPassword
                              ? context.l10n.showPasswordConfirmation
                              : context.l10n.hidePasswordConfirmation,
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
                        message: _confirmationFailure!.localized(context.l10n),
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
                          : Text(context.l10n.resetPassword),
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
                        _isRequestingOtp
                            ? context.l10n.sending
                            : context.l10n.resendCode,
                      ),
                    ),
                    if (_showRequestMessage) ...[
                      const SizedBox(height: 16),
                      _buildMessage(
                        context,
                        key: const Key('password-reset-otp-resend-success'),
                        message: _requestSuccessMessage,
                        isError: false,
                      ),
                    ],
                    if (_requestFailure != null) ...[
                      const SizedBox(height: 16),
                      _buildMessage(
                        context,
                        key: const Key('password-reset-otp-resend-error'),
                        message: _requestFailure!.localized(context.l10n),
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
      title: context.l10n.resetCodeUnavailable,
      subtitle: context.l10n.requestResetCodeDescription,
      children: [
        FilledButton(
          key: const Key('password-reset-otp-request-new-button'),
          onPressed: () => context.go('/forgot-password'),
          child: Text(context.l10n.requestNewCode),
        ),
        const SizedBox(height: 12),
        TextButton(
          key: const Key('password-reset-otp-unavailable-login-button'),
          onPressed: () => context.go('/login'),
          child: Text(context.l10n.backToLogin),
        ),
      ],
    );
  }

  Widget _buildSuccess(BuildContext context) {
    return _buildShell(
      context,
      icon: Icons.check_circle_outline_rounded,
      title: context.l10n.resetComplete,
      subtitle: context.l10n.resetCompleteDescription,
      children: [
        FilledButton(
          key: const Key('password-reset-otp-success-login-button'),
          onPressed: () => context.go('/login'),
          child: Text(context.l10n.goToLogin),
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

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/localization/l10n.dart';
import '../data/auth_repository.dart';
import '../domain/auth_failure.dart';
import 'auth_controller.dart';

class ResetPasswordScreen extends ConsumerStatefulWidget {
  const ResetPasswordScreen({super.key, this.token});

  final String? token;

  @override
  ConsumerState<ResetPasswordScreen> createState() =>
      _ResetPasswordScreenState();
}

class _ResetPasswordScreenState extends ConsumerState<ResetPasswordScreen> {
  static const int _minimumPasswordLength = 15;
  static const int _maximumPasswordLength = 128;
  static const int _maximumTokenLength = 512;

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();

  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _isSubmitting = false;
  bool _isComplete = false;
  bool _isInvalidLink = false;
  AuthFailure? _failure;

  @override
  void dispose() {
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  bool _isUsableToken(String token) {
    return token.trim().isNotEmpty && token.runes.length <= _maximumTokenLength;
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

  Future<void> _submit() async {
    if (_isSubmitting) {
      return;
    }

    final token = widget.token;
    if (token == null || !_isUsableToken(token)) {
      setState(() {
        _isInvalidLink = true;
      });
      return;
    }

    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isSubmitting = true;
      _failure = null;
    });

    try {
      final session = await ref.read(authControllerProvider.future);

      if (!mounted) {
        return;
      }

      await ref
          .read(authRepositoryProvider)
          .confirmPasswordReset(
            token: token,
            newPassword: _passwordController.text,
          );

      if (!mounted) {
        return;
      }

      if (session.isAuthenticated) {
        try {
          await ref.read(authControllerProvider.notifier).logout();
        } catch (_) {
          // logout() still transitions global auth state to unauthenticated.
        }
      }

      if (!mounted) {
        return;
      }

      _passwordController.clear();
      _confirmPasswordController.clear();

      setState(() {
        _isSubmitting = false;
        _isComplete = true;
      });
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _failure = failure;
        _isInvalidLink = failure.type == AuthFailureType.passwordResetInvalid;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _failure = AuthFailure.unexpected();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final token = widget.token;
    final hasUsableToken = token != null && _isUsableToken(token);

    if (_isComplete) {
      return _buildSuccess(context);
    }

    if (!hasUsableToken || _isInvalidLink) {
      return _buildUnavailable(context);
    }

    return PopScope(
      canPop: !_isSubmitting,
      child: Scaffold(
        key: const Key('reset-password-screen'),
        body: SafeArea(
          child: LocalizedForm(
            key: _formKey,
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
                        child: const Icon(
                          Icons.password_rounded,
                          color: Colors.white,
                          size: 32,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      context.l10n.newPasswordTitle,
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      context.l10n.newPasswordDescription,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 32),
                    TextFormField(
                      key: const Key('reset-password-field'),
                      controller: _passwordController,
                      validator: _validatePassword,
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
                          onPressed: () {
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
                      key: const Key('reset-password-confirm-field'),
                      controller: _confirmPasswordController,
                      validator: _validateConfirmPassword,
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
                          onPressed: () {
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
                    if (_failure != null) ...[
                      const SizedBox(height: 16),
                      Text(
                        _failure!.localized(context.l10n),
                        key: const Key('reset-password-error-message'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ],
                    const SizedBox(height: 24),
                    FilledButton(
                      key: const Key('reset-password-submit-button'),
                      onPressed: _isSubmitting ? null : _submit,
                      child: _isSubmitting
                          ? const SizedBox(
                              key: Key('reset-password-loading-indicator'),
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : Text(context.l10n.resetPassword),
                    ),
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
      icon: Icons.link_off_rounded,
      title: context.l10n.resetLinkUnavailable,
      subtitle: AuthFailure.invalidPasswordReset().localized(context.l10n),
      children: [
        FilledButton(
          key: const Key('reset-password-request-new-button'),
          onPressed: () => context.go('/forgot-password'),
          child: Text(context.l10n.requestNewResetLink),
        ),
        const SizedBox(height: 12),
        TextButton(
          key: const Key('reset-password-unavailable-login-button'),
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
          key: const Key('reset-password-success-login-button'),
          onPressed: () => context.go('/login'),
          child: Text(context.l10n.goToLogin),
        ),
      ],
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
      key: const Key('reset-password-screen'),
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

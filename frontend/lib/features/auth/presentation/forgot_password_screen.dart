import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../data/auth_repository.dart';
import '../domain/auth_failure.dart';

class ForgotPasswordScreen extends ConsumerStatefulWidget {
  const ForgotPasswordScreen({super.key});

  @override
  ConsumerState<ForgotPasswordScreen> createState() =>
      _ForgotPasswordScreenState();
}

class _ForgotPasswordScreenState extends ConsumerState<ForgotPasswordScreen> {
  static final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
  static const String _successMessage =
      'If an account with that email exists, password reset instructions have been sent.';

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final TextEditingController _emailController = TextEditingController();

  bool _isSubmitting = false;
  bool _isSendingLink = false;
  bool _isComplete = false;
  AuthFailure? _failure;

  @override
  void dispose() {
    _emailController.dispose();
    super.dispose();
  }

  String? _validateEmail(String? value) {
    final email = value?.trim() ?? '';

    if (email.isEmpty) {
      return 'Email is required.';
    }

    if (!_emailPattern.hasMatch(email)) {
      return 'Enter a valid email address.';
    }

    return null;
  }

  Future<void> _requestOtp() async {
    if (_isSubmitting) {
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
      final email = _emailController.text.trim().toLowerCase();
      await ref
          .read(authRepositoryProvider)
          .requestPasswordResetOtp(email: email);

      if (!mounted) {
        return;
      }

      context.go('/reset-password/code', extra: email);
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _failure = failure;
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

  Future<void> _sendResetLink() async {
    if (_isSubmitting) {
      return;
    }

    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isSubmitting = true;
      _isSendingLink = true;
      _failure = null;
    });

    try {
      await ref
          .read(authRepositoryProvider)
          .requestPasswordReset(
            email: _emailController.text.trim().toLowerCase(),
          );

      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _isSendingLink = false;
        _isComplete = true;
      });
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _isSendingLink = false;
        _failure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isSubmitting = false;
        _isSendingLink = false;
        _failure = AuthFailure.unexpected();
      });
    }
  }

  void _goBack() {
    if (_isSubmitting) {
      return;
    }

    if (context.canPop()) {
      context.pop();
      return;
    }

    context.go('/login');
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isSubmitting,
      child: Scaffold(
        key: const Key('forgot-password-screen'),
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
                        key: const Key('forgot-password-back-button'),
                        tooltip: 'Back to login',
                        onPressed: _isSubmitting ? null : _goBack,
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
                          Icons.lock_reset_rounded,
                          color: Colors.white,
                          size: 32,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    Text(
                      _isComplete ? 'Check your email' : 'Forgot password?',
                      style: Theme.of(context).textTheme.headlineMedium,
                    ),
                    const SizedBox(height: 10),
                    Text(
                      _isComplete
                          ? _successMessage
                          : 'Enter your email and Mealio will send a six-digit password reset code if an account exists.',
                      key: _isComplete
                          ? const Key('forgot-password-success-message')
                          : null,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    if (!_isComplete) ...[
                      const SizedBox(height: 32),
                      TextFormField(
                        key: const Key('forgot-password-email-field'),
                        controller: _emailController,
                        validator: _validateEmail,
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.done,
                        autofillHints: const [AutofillHints.email],
                        onFieldSubmitted: (_) => _requestOtp(),
                        decoration: const InputDecoration(
                          labelText: 'Email',
                          hintText: 'you@example.com',
                          prefixIcon: Icon(Icons.email_outlined),
                        ),
                      ),
                      if (_failure != null) ...[
                        const SizedBox(height: 16),
                        Text(
                          _failure!.message,
                          key: const Key('forgot-password-error-message'),
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.error,
                          ),
                        ),
                      ],
                      const SizedBox(height: 24),
                      FilledButton(
                        key: const Key('forgot-password-submit-button'),
                        onPressed: _isSubmitting ? null : _requestOtp,
                        child: _isSubmitting && !_isSendingLink
                            ? const SizedBox(
                                key: Key('forgot-password-loading-indicator'),
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Send reset code'),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton(
                        key: const Key('forgot-password-link-button'),
                        onPressed: _isSubmitting ? null : _sendResetLink,
                        child: _isSubmitting && _isSendingLink
                            ? const SizedBox(
                                key: Key(
                                  'forgot-password-link-loading-indicator',
                                ),
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Send reset link instead'),
                      ),
                    ] else ...[
                      const SizedBox(height: 28),
                      FilledButton(
                        key: const Key('forgot-password-login-button'),
                        onPressed: () => context.go('/login'),
                        child: const Text('Back to login'),
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
}

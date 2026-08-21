import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import 'auth_controller.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key, this.registrationSuccessEmail});

  final String? registrationSuccessEmail;

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  static final RegExp _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _emailController;
  late final TextEditingController _passwordController;

  bool _obscurePassword = true;
  bool _showRegistrationSuccess = false;

  @override
  void initState() {
    super.initState();
    _emailController = TextEditingController(
      text: widget.registrationSuccessEmail ?? '',
    );
    _passwordController = TextEditingController();
    _showRegistrationSuccess = widget.registrationSuccessEmail != null;
  }

  @override
  void didUpdateWidget(covariant LoginScreen oldWidget) {
    super.didUpdateWidget(oldWidget);

    final registrationSuccessEmail = widget.registrationSuccessEmail;

    if (registrationSuccessEmail != oldWidget.registrationSuccessEmail) {
      _showRegistrationSuccess = registrationSuccessEmail != null;

      if (registrationSuccessEmail != null) {
        _emailController.text = registrationSuccessEmail;
        _passwordController.clear();
        _obscurePassword = true;
      }
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
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

  String? _validatePassword(String? value) {
    if (value == null || value.isEmpty) {
      return 'Password is required.';
    }

    return null;
  }

  void _submit() {
    final session = ref.read(authControllerProvider).asData?.value;

    if (session?.isLoginInProgress == true) {
      return;
    }

    if (!_formKey.currentState!.validate()) {
      return;
    }

    if (_showRegistrationSuccess) {
      setState(() {
        _showRegistrationSuccess = false;
      });
    }

    ref
        .read(authControllerProvider.notifier)
        .login(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final session = authState.asData?.value;
    final isLoginInProgress = session?.isLoginInProgress ?? false;
    final failure = _showRegistrationSuccess ? null : session?.failure;

    return Scaffold(
      key: const Key('login-screen'),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(24, 32, 24, 24),
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
                    Icons.restaurant_rounded,
                    color: Colors.white,
                    size: 34,
                  ),
                ),
              ),
              const SizedBox(height: 28),
              Text(
                'Welcome to Mealio',
                style: Theme.of(context).textTheme.headlineMedium,
              ),
              const SizedBox(height: 10),
              Text(
                'Sign in to manage your pantry, recipes and meal plans.',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
              if (_showRegistrationSuccess) ...[
                const SizedBox(height: 20),
                Container(
                  key: const Key('registration-success-message'),
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: AppColors.sage.withValues(alpha: 0.18),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: AppColors.sage),
                  ),
                  child: const Text(
                    'Account created successfully. You can now sign in.',
                  ),
                ),
              ],
              const SizedBox(height: 32),
              TextFormField(
                key: const Key('login-email-field'),
                controller: _emailController,
                validator: _validateEmail,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autofillHints: const [AutofillHints.email],
                decoration: const InputDecoration(
                  labelText: 'Email',
                  hintText: 'you@example.com',
                  prefixIcon: Icon(Icons.email_outlined),
                ),
              ),
              const SizedBox(height: 16),
              TextFormField(
                key: const Key('login-password-field'),
                controller: _passwordController,
                validator: _validatePassword,
                obscureText: _obscurePassword,
                textInputAction: TextInputAction.done,
                autofillHints: const [AutofillHints.password],
                onFieldSubmitted: (_) => _submit(),
                decoration: InputDecoration(
                  labelText: 'Password',
                  prefixIcon: const Icon(Icons.lock_outline_rounded),
                  suffixIcon: IconButton(
                    tooltip: _obscurePassword
                        ? 'Show password'
                        : 'Hide password',
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
              Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  key: const Key('forgot-password-button'),
                  onPressed: isLoginInProgress
                      ? null
                      : () => context.push('/forgot-password'),
                  child: const Text('Forgot password?'),
                ),
              ),
              if (failure != null) ...[
                const SizedBox(height: 16),
                Text(
                  failure.message,
                  key: const Key('login-error-message'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 24),
              FilledButton(
                key: const Key('login-button'),
                onPressed: isLoginInProgress ? null : _submit,
                child: isLoginInProgress
                    ? const SizedBox(
                        key: Key('login-loading-indicator'),
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Login'),
              ),
              const SizedBox(height: 24),
              TextButton(
                key: const Key('open-register-button'),
                onPressed: isLoginInProgress
                    ? null
                    : () => context.push('/register'),
                child: const Text('New to Mealio? Create an account'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

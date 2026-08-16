import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../data/auth_repository.dart';
import '../domain/auth_failure.dart';
import '../domain/auth_user.dart';
import 'auth_controller.dart';

class VerifyEmailScreen extends ConsumerStatefulWidget {
  const VerifyEmailScreen({super.key, this.email, this.token});

  final String? email;
  final String? token;

  @override
  ConsumerState<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

enum _ConfirmationStatus { idle, loading, success, invalid, error, syncError }

class _VerifyEmailScreenState extends ConsumerState<VerifyEmailScreen> {
  static const int _maximumTokenLength = 512;
  static const String _resendSuccessMessage =
      'If verification is needed, instructions have been sent.';

  bool _isResending = false;
  bool _isRefreshingStatus = false;
  String? _resendMessage;
  AuthFailure? _resendFailure;
  String? _statusMessage;
  AuthFailure? _statusFailure;

  late _ConfirmationStatus _confirmationStatus;
  AuthFailure? _confirmationFailure;

  @override
  void initState() {
    super.initState();

    final token = widget.token;
    if (token == null) {
      _confirmationStatus = _ConfirmationStatus.idle;
      return;
    }

    if (!_isUsableToken(token)) {
      _confirmationStatus = _ConfirmationStatus.invalid;
      return;
    }

    _confirmationStatus = _ConfirmationStatus.loading;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        unawaited(_confirmEmail(token));
      }
    });
  }

  bool _isUsableToken(String token) {
    final normalizedToken = token.trim();
    return normalizedToken.isNotEmpty &&
        normalizedToken.runes.length <= _maximumTokenLength;
  }

  Future<void> _confirmEmail(String token) async {
    final session = await ref.read(authControllerProvider.future);

    if (!mounted) {
      return;
    }

    if (session.user?.emailVerified == true) {
      setState(() {
        _confirmationStatus = _ConfirmationStatus.success;
        _confirmationFailure = null;
      });
      return;
    }

    try {
      await ref
          .read(authRepositoryProvider)
          .confirmEmailVerification(token: token);

      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = _ConfirmationStatus.success;
        _confirmationFailure = null;
      });

      unawaited(_synchronizeAuthenticatedUser());
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationFailure = failure;
        _confirmationStatus =
            failure.type == AuthFailureType.emailVerificationInvalid
            ? _ConfirmationStatus.invalid
            : _ConfirmationStatus.error;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationFailure = AuthFailure.unexpected();
        _confirmationStatus = _ConfirmationStatus.error;
      });
    }
  }

  Future<void> _synchronizeAuthenticatedUser() async {
    try {
      final session = await ref.read(authControllerProvider.future);

      if (!mounted || !session.isAuthenticated) {
        return;
      }

      final user = await ref
          .read(authControllerProvider.notifier)
          .reloadCurrentUser();

      if (!mounted) {
        return;
      }

      if (user != null && !user.emailVerified) {
        setState(() {
          _confirmationStatus = _ConfirmationStatus.syncError;
        });
      }
    } on AuthFailure {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = _ConfirmationStatus.syncError;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = _ConfirmationStatus.syncError;
      });
    }
  }

  Future<void> _retrySynchronization() async {
    if (_isRefreshingStatus) {
      return;
    }

    setState(() {
      _isRefreshingStatus = true;
    });

    try {
      final user = await ref
          .read(authControllerProvider.notifier)
          .reloadCurrentUser();

      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = user == null || user.emailVerified
            ? _ConfirmationStatus.success
            : _ConfirmationStatus.syncError;
        _isRefreshingStatus = false;
      });
    } on AuthFailure {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = _ConfirmationStatus.syncError;
        _isRefreshingStatus = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _confirmationStatus = _ConfirmationStatus.syncError;
        _isRefreshingStatus = false;
      });
    }
  }

  Future<void> _resend(String email) async {
    if (_isResending) {
      return;
    }

    setState(() {
      _isResending = true;
      _resendMessage = null;
      _resendFailure = null;
    });

    try {
      await ref
          .read(authRepositoryProvider)
          .requestEmailVerification(email: email);

      if (!mounted) {
        return;
      }

      setState(() {
        _isResending = false;
        _resendMessage = _resendSuccessMessage;
      });
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isResending = false;
        _resendFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isResending = false;
        _resendFailure = AuthFailure.unexpected();
      });
    }
  }

  Future<void> _refreshVerificationStatus() async {
    if (_isRefreshingStatus) {
      return;
    }

    setState(() {
      _isRefreshingStatus = true;
      _statusMessage = null;
      _statusFailure = null;
    });

    try {
      final user = await ref
          .read(authControllerProvider.notifier)
          .reloadCurrentUser();

      if (!mounted) {
        return;
      }

      setState(() {
        _isRefreshingStatus = false;
        if (user?.emailVerified != true) {
          _statusMessage = 'Your email is not verified yet.';
        }
      });
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRefreshingStatus = false;
        _statusFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRefreshingStatus = false;
        _statusFailure = AuthFailure.unexpected();
      });
    }
  }

  void _continue({required bool isAuthenticated}) {
    if (isAuthenticated) {
      context.go('/home');
      return;
    }

    final email = widget.email?.trim();
    context.go(
      '/login',
      extra: email != null && email.isNotEmpty ? email : null,
    );
  }

  @override
  Widget build(BuildContext context) {
    final authSession = ref.watch(authControllerProvider).asData?.value;
    final currentUser = authSession?.user;
    final isAuthenticated = currentUser != null;
    final routeEmail = widget.email?.trim();
    final email =
        currentUser?.email ??
        (routeEmail != null && routeEmail.isNotEmpty ? routeEmail : null);

    if (currentUser != null && currentUser.emailVerified) {
      return _buildVerified(
        context,
        isAuthenticated: true,
        email: currentUser.email,
      );
    }

    if (widget.token != null) {
      return _buildConfirmation(
        context,
        currentUser: currentUser,
        isAuthenticated: isAuthenticated,
      );
    }

    if (email == null) {
      return _buildMissingLink(context, isAuthenticated: isAuthenticated);
    }

    return _buildPending(
      context,
      email: email,
      isAuthenticated: isAuthenticated,
    );
  }

  Widget _buildPending(
    BuildContext context, {
    required String email,
    required bool isAuthenticated,
  }) {
    final actions = <Widget>[
      FilledButton.icon(
        key: const Key('verify-email-resend-button'),
        onPressed: _isResending ? null : () => _resend(email),
        icon: _isResending
            ? const SizedBox(
                key: Key('verify-email-resend-loading'),
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.mark_email_unread_outlined),
        label: Text(_isResending ? 'Sending…' : 'Resend email'),
      ),
      if (isAuthenticated) ...[
        const SizedBox(height: 12),
        OutlinedButton(
          key: const Key('verify-email-refresh-button'),
          onPressed: _isRefreshingStatus ? null : _refreshVerificationStatus,
          child: _isRefreshingStatus
              ? const SizedBox(
                  key: Key('verify-email-refresh-loading'),
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Text("I've verified my email"),
        ),
      ],
      const SizedBox(height: 12),
      TextButton(
        key: const Key('verify-email-continue-button'),
        onPressed: () => _continue(isAuthenticated: isAuthenticated),
        child: Text(
          isAuthenticated ? 'Continue to Mealio' : 'Continue to login',
        ),
      ),
    ];

    return _buildShell(
      context,
      icon: Icons.mark_email_read_outlined,
      title: 'Verify your email',
      subtitle:
          'Check your inbox and follow the verification link to confirm your email address.',
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
          decoration: BoxDecoration(
            color: AppColors.cream,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Verification email',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 6),
              Text(
                email,
                key: const Key('verify-email-address'),
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        Text(
          'The initial verification email is requested automatically when your account is created. You only need Resend if you want another verification email.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        if (_resendMessage != null) ...[
          const SizedBox(height: 18),
          _buildInfoMessage(
            context,
            key: const Key('verify-email-resend-success'),
            icon: Icons.info_outline_rounded,
            message: _resendMessage!,
          ),
        ],
        if (_resendFailure != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-resend-error'),
            message: _resendFailure!.message,
          ),
        ],
        if (_statusMessage != null) ...[
          const SizedBox(height: 18),
          _buildInfoMessage(
            context,
            key: const Key('verify-email-status-message'),
            icon: Icons.schedule_rounded,
            message: _statusMessage!,
          ),
        ],
        if (_statusFailure != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-status-error'),
            message: _statusFailure!.message,
          ),
        ],
        const SizedBox(height: 28),
        ...actions,
      ],
    );
  }

  Widget _buildConfirmation(
    BuildContext context, {
    required AuthUser? currentUser,
    required bool isAuthenticated,
  }) {
    switch (_confirmationStatus) {
      case _ConfirmationStatus.loading:
        return _buildShell(
          context,
          icon: Icons.verified_outlined,
          title: 'Verifying your email',
          subtitle: 'Mealio is securely confirming your verification link.',
          children: const [
            SizedBox(height: 12),
            Center(
              child: CircularProgressIndicator(
                key: Key('verify-email-confirm-loading'),
              ),
            ),
          ],
        );
      case _ConfirmationStatus.success:
        return _buildVerified(
          context,
          isAuthenticated: isAuthenticated,
          email: currentUser?.email,
        );
      case _ConfirmationStatus.invalid:
        return _buildConfirmationError(
          context,
          title: 'Verification link unavailable',
          message: AuthFailure.invalidEmailVerification().message,
          isAuthenticated: isAuthenticated,
          retryable: false,
        );
      case _ConfirmationStatus.error:
        return _buildConfirmationError(
          context,
          title: 'Could not verify email',
          message:
              _confirmationFailure?.message ?? AuthFailure.unexpected().message,
          isAuthenticated: isAuthenticated,
          retryable: _isUsableToken(widget.token ?? ''),
        );
      case _ConfirmationStatus.syncError:
        return _buildShell(
          context,
          icon: Icons.verified_rounded,
          title: 'Email verified',
          subtitle:
              'Your verification was accepted, but Mealio could not refresh your signed-in account.',
          children: [
            _buildInfoMessage(
              context,
              key: const Key('verify-email-sync-message'),
              icon: Icons.sync_problem_rounded,
              message:
                  'Your email is verified on the server. Refresh your account state before continuing.',
            ),
            const SizedBox(height: 24),
            FilledButton(
              key: const Key('verify-email-sync-retry-button'),
              onPressed: _isRefreshingStatus ? null : _retrySynchronization,
              child: _isRefreshingStatus
                  ? const SizedBox(
                      key: Key('verify-email-sync-loading'),
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Refresh account'),
            ),
            const SizedBox(height: 12),
            TextButton(
              key: const Key('verify-email-sync-continue-button'),
              onPressed: () => _continue(isAuthenticated: isAuthenticated),
              child: Text(
                isAuthenticated ? 'Continue to Mealio' : 'Go to login',
              ),
            ),
          ],
        );
      case _ConfirmationStatus.idle:
        return _buildMissingLink(context, isAuthenticated: isAuthenticated);
    }
  }

  Widget _buildVerified(
    BuildContext context, {
    required bool isAuthenticated,
    String? email,
  }) {
    return _buildShell(
      context,
      icon: Icons.verified_rounded,
      title: 'Email verified',
      subtitle:
          'Your email address is confirmed. You can continue using Mealio.',
      children: [
        if (email != null) ...[
          _buildInfoMessage(
            context,
            key: const Key('verify-email-verified-address'),
            icon: Icons.alternate_email_rounded,
            message: email,
          ),
          const SizedBox(height: 24),
        ],
        FilledButton(
          key: const Key('verify-email-success-continue-button'),
          onPressed: () => _continue(isAuthenticated: isAuthenticated),
          child: Text(isAuthenticated ? 'Continue to Mealio' : 'Go to login'),
        ),
      ],
    );
  }

  Widget _buildMissingLink(
    BuildContext context, {
    required bool isAuthenticated,
  }) {
    return _buildShell(
      context,
      icon: Icons.link_off_rounded,
      title: 'Verification link unavailable',
      subtitle:
          'Open the verification link from your email, or return to Mealio and request another email.',
      children: [
        FilledButton(
          key: const Key('verify-email-missing-continue-button'),
          onPressed: () => _continue(isAuthenticated: isAuthenticated),
          child: Text(isAuthenticated ? 'Continue to Mealio' : 'Go to login'),
        ),
      ],
    );
  }

  Widget _buildConfirmationError(
    BuildContext context, {
    required String title,
    required String message,
    required bool isAuthenticated,
    required bool retryable,
  }) {
    return _buildShell(
      context,
      icon: Icons.error_outline_rounded,
      title: title,
      subtitle: message,
      children: [
        if (retryable) ...[
          FilledButton(
            key: const Key('verify-email-confirm-retry-button'),
            onPressed: () {
              final token = widget.token;
              if (token == null || !_isUsableToken(token)) {
                return;
              }

              setState(() {
                _confirmationStatus = _ConfirmationStatus.loading;
                _confirmationFailure = null;
              });
              unawaited(_confirmEmail(token));
            },
            child: const Text('Try again'),
          ),
          const SizedBox(height: 12),
        ],
        TextButton(
          key: const Key('verify-email-error-continue-button'),
          onPressed: () => _continue(isAuthenticated: isAuthenticated),
          child: Text(isAuthenticated ? 'Continue to Mealio' : 'Go to login'),
        ),
      ],
    );
  }

  Widget _buildInfoMessage(
    BuildContext context, {
    required Key key,
    required IconData icon,
    required String message,
  }) {
    return Container(
      key: key,
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cream,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: AppColors.forest, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorMessage(
    BuildContext context, {
    required Key key,
    required String message,
  }) {
    return Container(
      key: key,
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.error_outline_rounded,
            color: Theme.of(context).colorScheme.onErrorContainer,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: Theme.of(context).colorScheme.onErrorContainer,
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
      key: const Key('verify-email-screen'),
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

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/localization/l10n.dart';
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

enum _VerificationMode { link, otp }

enum _ConfirmationStatus { idle, loading, success, invalid, error, syncError }

class _VerifyEmailScreenState extends ConsumerState<VerifyEmailScreen> {
  static const int _maximumTokenLength = 512;
  static final RegExp _otpPattern = RegExp(r'^[0-9]{6}$');
  String get _resendSuccessMessage => context.l10n.verificationInstructionsSent;
  String get _otpRequestSuccessMessage => context.l10n.verificationCodeSent;

  final TextEditingController _otpController = TextEditingController();
  final FocusNode _otpFocusNode = FocusNode();

  bool _isResending = false;
  bool _isRefreshingStatus = false;
  bool _isRequestingOtp = false;
  bool _isConfirmingOtp = false;
  bool _resendMessageVisible = false;
  AuthFailure? _resendFailure;
  bool _statusMessageVisible = false;
  AuthFailure? _statusFailure;
  bool _otpRequestMessageVisible = false;
  AuthFailure? _otpRequestFailure;
  AuthFailure? _otpConfirmationFailure;

  _VerificationMode _verificationMode = _VerificationMode.link;

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

  @override
  void dispose() {
    _otpController.clear();
    _otpController.dispose();
    _otpFocusNode.dispose();
    super.dispose();
  }

  void _showOtpMode() {
    if (_verificationMode == _VerificationMode.otp) {
      return;
    }

    setState(() {
      _verificationMode = _VerificationMode.otp;
      _otpRequestMessageVisible = false;
      _otpRequestFailure = null;
      _otpConfirmationFailure = null;
    });

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _otpFocusNode.requestFocus();
      }
    });
  }

  void _showLinkMode() {
    if (_isRequestingOtp || _isConfirmingOtp) {
      return;
    }

    _otpController.clear();
    _otpFocusNode.unfocus();
    setState(() {
      _verificationMode = _VerificationMode.link;
      _otpRequestMessageVisible = false;
      _otpRequestFailure = null;
      _otpConfirmationFailure = null;
    });
  }

  Future<void> _requestOtp(String email) async {
    if (_isRequestingOtp || _isConfirmingOtp) {
      return;
    }

    setState(() {
      _isRequestingOtp = true;
      _otpRequestMessageVisible = false;
      _otpRequestFailure = null;
    });

    try {
      await ref
          .read(authRepositoryProvider)
          .requestEmailVerificationOtp(email: email);

      if (!mounted) {
        return;
      }

      setState(() {
        _isRequestingOtp = false;
        _otpRequestMessageVisible = true;
      });
      _otpFocusNode.requestFocus();
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRequestingOtp = false;
        _otpRequestFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isRequestingOtp = false;
        _otpRequestFailure = AuthFailure.unexpected();
      });
    }
  }

  Future<void> _confirmOtp(String email) async {
    if (_isRequestingOtp || _isConfirmingOtp) {
      return;
    }

    final code = _otpController.text;
    if (!_otpPattern.hasMatch(code)) {
      return;
    }

    setState(() {
      _isConfirmingOtp = true;
      _otpConfirmationFailure = null;
    });

    try {
      await ref
          .read(authRepositoryProvider)
          .confirmEmailVerificationOtp(email: email, code: code);

      if (!mounted) {
        return;
      }

      _otpController.clear();
      _otpFocusNode.unfocus();
      setState(() {
        _isConfirmingOtp = false;
        _confirmationStatus = _ConfirmationStatus.success;
      });

      unawaited(_synchronizeAuthenticatedUser());
    } on AuthFailure catch (failure) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isConfirmingOtp = false;
        _otpConfirmationFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _isConfirmingOtp = false;
        _otpConfirmationFailure = AuthFailure.unexpected();
      });
    }
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
      _resendMessageVisible = false;
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
        _resendMessageVisible = true;
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
      _statusMessageVisible = false;
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
          _statusMessageVisible = true;
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

    final email = widget.email?.trim().toLowerCase();
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
    final routeEmail = widget.email?.trim().toLowerCase();
    final email =
        currentUser?.email.trim().toLowerCase() ??
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

    if (_confirmationStatus == _ConfirmationStatus.success ||
        _confirmationStatus == _ConfirmationStatus.syncError) {
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
    if (_verificationMode == _VerificationMode.otp) {
      return _buildOtpPending(
        context,
        email: email,
        isAuthenticated: isAuthenticated,
      );
    }

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
        label: Text(
          _isResending ? context.l10n.sending : context.l10n.resendEmail,
        ),
      ),
      const SizedBox(height: 12),
      OutlinedButton.icon(
        key: const Key('verify-email-use-code-button'),
        onPressed: _showOtpMode,
        icon: const Icon(Icons.password_rounded),
        label: Text(context.l10n.verifyWithCode),
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
              : Text(context.l10n.alreadyVerified),
        ),
      ],
      const SizedBox(height: 12),
      TextButton(
        key: const Key('verify-email-continue-button'),
        onPressed: () => _continue(isAuthenticated: isAuthenticated),
        child: Text(
          isAuthenticated
              ? context.l10n.continueToMealio
              : context.l10n.continueToLogin,
        ),
      ),
    ];

    return _buildShell(
      context,
      icon: Icons.mark_email_read_outlined,
      title: context.l10n.verifyEmail,
      subtitle: context.l10n.verifyEmailDescription,
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
                context.l10n.verificationEmail,
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
          context.l10n.verificationInitialHint,
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        if (_resendMessageVisible) ...[
          const SizedBox(height: 18),
          _buildInfoMessage(
            context,
            key: const Key('verify-email-resend-success'),
            icon: Icons.info_outline_rounded,
            message: _resendSuccessMessage,
          ),
        ],
        if (_resendFailure != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-resend-error'),
            message: _resendFailure!.localized(context.l10n),
          ),
        ],
        if (_statusMessageVisible) ...[
          const SizedBox(height: 18),
          _buildInfoMessage(
            context,
            key: const Key('verify-email-status-message'),
            icon: Icons.schedule_rounded,
            message: context.l10n.emailNotVerified,
          ),
        ],
        if (_statusFailure != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-status-error'),
            message: _statusFailure!.localized(context.l10n),
          ),
        ],
        const SizedBox(height: 28),
        ...actions,
      ],
    );
  }

  Widget _buildOtpPending(
    BuildContext context, {
    required String email,
    required bool isAuthenticated,
  }) {
    final hasCompleteCode = _otpPattern.hasMatch(_otpController.text);
    final operationInProgress = _isRequestingOtp || _isConfirmingOtp;

    return _buildShell(
      context,
      icon: Icons.password_rounded,
      title: context.l10n.verifyWithCode,
      subtitle: context.l10n.verifyCodeDescription,
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
                context.l10n.emailAddress,
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 6),
              Text(
                email,
                key: const Key('verify-email-otp-address'),
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        FilledButton.icon(
          key: const Key('verify-email-otp-request-button'),
          onPressed: operationInProgress ? null : () => _requestOtp(email),
          icon: _isRequestingOtp
              ? const SizedBox(
                  key: Key('verify-email-otp-request-loading'),
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.mark_email_unread_outlined),
          label: Text(
            _isRequestingOtp
                ? context.l10n.sending
                : context.l10n.sendVerificationCode,
          ),
        ),
        if (_otpRequestMessageVisible) ...[
          const SizedBox(height: 18),
          _buildInfoMessage(
            context,
            key: const Key('verify-email-otp-request-success'),
            icon: Icons.info_outline_rounded,
            message: _otpRequestSuccessMessage,
          ),
        ],
        if (_otpRequestFailure != null) ...[
          const SizedBox(height: 18),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-otp-request-error'),
            message: _otpRequestFailure!.localized(context.l10n),
          ),
        ],
        const SizedBox(height: 22),
        TextField(
          key: const Key('verify-email-otp-field'),
          controller: _otpController,
          focusNode: _otpFocusNode,
          enabled: !_isConfirmingOtp,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.done,
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
              _otpConfirmationFailure = null;
            });
          },
          onSubmitted: (_) {
            if (!operationInProgress && hasCompleteCode) {
              unawaited(_confirmOtp(email));
            }
          },
          decoration: InputDecoration(
            labelText: context.l10n.verificationCodeLabel,
            hintText: context.l10n.otpHint,
            prefixIcon: Icon(Icons.pin_outlined),
          ),
        ),
        if (_otpConfirmationFailure != null) ...[
          const SizedBox(height: 14),
          _buildErrorMessage(
            context,
            key: const Key('verify-email-otp-confirm-error'),
            message: _otpConfirmationFailure!.localized(context.l10n),
          ),
        ],
        const SizedBox(height: 18),
        FilledButton(
          key: const Key('verify-email-otp-confirm-button'),
          onPressed: operationInProgress || !hasCompleteCode
              ? null
              : () => _confirmOtp(email),
          child: _isConfirmingOtp
              ? const SizedBox(
                  key: Key('verify-email-otp-confirm-loading'),
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(context.l10n.confirmCode),
        ),
        const SizedBox(height: 12),
        OutlinedButton(
          key: const Key('verify-email-use-link-button'),
          onPressed: operationInProgress ? null : _showLinkMode,
          child: Text(context.l10n.useVerificationLink),
        ),
        const SizedBox(height: 12),
        TextButton(
          key: const Key('verify-email-otp-continue-button'),
          onPressed: operationInProgress
              ? null
              : () => _continue(isAuthenticated: isAuthenticated),
          child: Text(
            isAuthenticated
                ? context.l10n.continueToMealio
                : context.l10n.continueToLogin,
          ),
        ),
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
          title: context.l10n.verifyingEmail,
          subtitle: context.l10n.verifyingEmailDescription,
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
          title: context.l10n.verificationLinkUnavailable,
          message: AuthFailure.invalidEmailVerification().localized(
            context.l10n,
          ),
          isAuthenticated: isAuthenticated,
          retryable: false,
        );
      case _ConfirmationStatus.error:
        return _buildConfirmationError(
          context,
          title: context.l10n.couldNotVerifyEmail,
          message: (_confirmationFailure ?? AuthFailure.unexpected()).localized(
            context.l10n,
          ),
          isAuthenticated: isAuthenticated,
          retryable: _isUsableToken(widget.token ?? ''),
        );
      case _ConfirmationStatus.syncError:
        return _buildShell(
          context,
          icon: Icons.verified_rounded,
          title: context.l10n.emailVerified,
          subtitle: context.l10n.verificationSyncError,
          children: [
            _buildInfoMessage(
              context,
              key: const Key('verify-email-sync-message'),
              icon: Icons.sync_problem_rounded,
              message: context.l10n.verificationSyncHint,
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
                  : Text(context.l10n.refreshAccount),
            ),
            const SizedBox(height: 12),
            TextButton(
              key: const Key('verify-email-sync-continue-button'),
              onPressed: () => _continue(isAuthenticated: isAuthenticated),
              child: Text(
                isAuthenticated
                    ? context.l10n.continueToMealio
                    : context.l10n.goToLogin,
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
      title: context.l10n.emailVerified,
      subtitle: context.l10n.emailVerifiedDescription,
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
          child: Text(
            isAuthenticated
                ? context.l10n.continueToMealio
                : context.l10n.goToLogin,
          ),
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
      title: context.l10n.verificationLinkUnavailable,
      subtitle: context.l10n.missingVerificationLink,
      children: [
        FilledButton(
          key: const Key('verify-email-missing-continue-button'),
          onPressed: () => _continue(isAuthenticated: isAuthenticated),
          child: Text(
            isAuthenticated
                ? context.l10n.continueToMealio
                : context.l10n.goToLogin,
          ),
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
            child: Text(context.l10n.tryAgain),
          ),
          const SizedBox(height: 12),
        ],
        TextButton(
          key: const Key('verify-email-error-continue-button'),
          onPressed: () => _continue(isAuthenticated: isAuthenticated),
          child: Text(
            isAuthenticated
                ? context.l10n.continueToMealio
                : context.l10n.goToLogin,
          ),
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

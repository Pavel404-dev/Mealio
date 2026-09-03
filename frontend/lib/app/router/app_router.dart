import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/auth_controller.dart';
import '../../features/auth/presentation/forgot_password_screen.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/password_reset_otp_screen.dart';
import '../../features/auth/presentation/register_screen.dart';
import '../../features/auth/presentation/reset_password_screen.dart';
import '../../features/auth/presentation/verify_email_screen.dart';
import '../../features/home/presentation/home_screen.dart';
import '../../features/splash/presentation/splash_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshNotifier = ValueNotifier<int>(0);

  ref.onDispose(refreshNotifier.dispose);
  ref.listen(authControllerProvider, (previous, next) {
    refreshNotifier.value++;
  });

  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: refreshNotifier,
    redirect: (context, state) {
      final authState = ref.read(authControllerProvider);
      final location = state.matchedLocation;
      final isVerificationRoute = location == '/verify-email';
      final isPasswordResetRoute = location == '/reset-password';
      final isPasswordResetOtpRoute = location == '/reset-password/code';
      final isPublicRecoveryRoute =
          isVerificationRoute ||
          isPasswordResetRoute ||
          isPasswordResetOtpRoute;

      if (authState.isLoading) {
        if (isPublicRecoveryRoute) {
          return null;
        }

        return location == '/splash' ? null : '/splash';
      }

      final session = authState.asData?.value;
      final isAuthenticated = session?.isAuthenticated ?? false;

      if (isAuthenticated) {
        if (location == '/splash' ||
            location == '/login' ||
            location == '/register') {
          return '/home';
        }

        return null;
      }

      final isPublicAuthRoute =
          location == '/login' ||
          location == '/register' ||
          location == '/forgot-password' ||
          isVerificationRoute ||
          isPasswordResetRoute ||
          isPasswordResetOtpRoute;

      if (!isPublicAuthRoute) {
        return '/login';
      }

      return null;
    },
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) {
          final extra = state.extra;
          return LoginScreen(
            registrationSuccessEmail: extra is String ? extra : null,
          );
        },
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      GoRoute(
        path: '/forgot-password',
        builder: (context, state) => const ForgotPasswordScreen(),
      ),
      GoRoute(
        path: '/reset-password/code',
        builder: (context, state) {
          final extra = state.extra;
          return PasswordResetOtpScreen(email: extra is String ? extra : null);
        },
      ),
      GoRoute(
        path: '/reset-password',
        builder: (context, state) =>
            ResetPasswordScreen(token: state.uri.queryParameters['token']),
      ),
      GoRoute(
        path: '/verify-email',
        builder: (context, state) {
          final extra = state.extra;
          return VerifyEmailScreen(
            email: extra is String ? extra : null,
            token: state.uri.queryParameters['token'],
          );
        },
      ),
      GoRoute(path: '/home', builder: (context, state) => const HomeScreen()),
    ],
  );
});

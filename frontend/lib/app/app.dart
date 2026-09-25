import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/localization/locale_controller.dart';
import '../l10n/generated/app_localizations.dart';
import 'router/app_router.dart';
import 'theme/app_theme.dart';

class MealioApp extends ConsumerWidget {
  const MealioApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);

    return MaterialApp.router(
      title: 'Mealio',
      locale: ref.watch(localeControllerProvider),
      localeListResolutionCallback: resolveAppLocale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      routerConfig: router,
    );
  }
}

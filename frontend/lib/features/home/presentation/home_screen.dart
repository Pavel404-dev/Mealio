import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/localization/l10n.dart';
import '../../../core/localization/language_button.dart';
import '../../auth/domain/auth_failure.dart';
import '../../auth/presentation/auth_controller.dart';

enum _HomeFeature { aiRecipe, mealPlan, shoppingList }

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  void _showPlaceholder(BuildContext context, _HomeFeature feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Builder(
          builder: (context) {
            final name = switch (feature) {
              _HomeFeature.aiRecipe => context.l10n.aiRecipe,
              _HomeFeature.mealPlan => context.l10n.mealPlan,
              _HomeFeature.shoppingList => context.l10n.shoppingList,
            };
            return Text(context.l10n.featureComingSoon(name));
          },
        ),
      ),
    );
  }

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(authControllerProvider.notifier).logout();
    } on AuthFailure catch (failure) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Builder(
            builder: (context) => Text(failure.localized(context.l10n)),
          ),
        ),
      );
    } catch (_) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Builder(
            builder: (context) => Text(context.l10n.unexpectedError),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).asData?.value.user;
    final fullName = user?.fullName?.trim();
    final greetingTarget = fullName != null && fullName.isNotEmpty
        ? fullName
        : user?.email;

    return Scaffold(
      key: const Key('home-screen'),
      appBar: AppBar(
        title: const Text('Mealio'),
        actions: [
          const LanguageButton(),
          IconButton(
            key: const Key('home-logout-button'),
            tooltip: context.l10n.logout,
            onPressed: () async {
              await _logout(context, ref);
            },
            icon: const Icon(Icons.logout_rounded),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          children: [
            Text(
              greetingTarget == null
                  ? context.l10n.greeting
                  : context.l10n.greetingNamed(greetingTarget),
              key: const Key('home-greeting'),
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              context.l10n.dashboardDescription,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 28),
            _FeatureCard(
              key: const Key('pantry-card'),
              title: context.l10n.pantry,
              description: context.l10n.pantryDescription,
              icon: Icons.kitchen_outlined,
              accentColor: AppColors.sage,
              onTap: () => context.push('/pantry'),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('ai-recipe-card'),
              title: context.l10n.aiRecipe,
              description: context.l10n.aiRecipeDescription,
              icon: Icons.auto_awesome_rounded,
              accentColor: AppColors.peach,
              onTap: () => _showPlaceholder(context, _HomeFeature.aiRecipe),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('meal-plan-card'),
              title: context.l10n.mealPlan,
              description: context.l10n.mealPlanDescription,
              icon: Icons.calendar_month_outlined,
              accentColor: const Color(0xFFB7C9E2),
              onTap: () => _showPlaceholder(context, _HomeFeature.mealPlan),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('shopping-list-card'),
              title: context.l10n.shoppingList,
              description: context.l10n.shoppingListDescription,
              icon: Icons.shopping_basket_outlined,
              accentColor: const Color(0xFFD8C4E8),
              onTap: () => _showPlaceholder(context, _HomeFeature.shoppingList),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeatureCard extends StatelessWidget {
  const _FeatureCard({
    required this.title,
    required this.description,
    required this.icon,
    required this.accentColor,
    required this.onTap,
    super.key,
  });

  final String title;
  final String description;
  final IconData icon;
  final Color accentColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      elevation: 0,
      color: Colors.white,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(24),
        side: const BorderSide(color: AppColors.border),
      ),
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Container(
                width: 58,
                height: 58,
                decoration: BoxDecoration(
                  color: accentColor.withValues(alpha: 0.45),
                  borderRadius: BorderRadius.circular(18),
                ),
                child: Icon(icon, color: AppColors.ink, size: 30),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 4),
                    Text(
                      description,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
            ],
          ),
        ),
      ),
    );
  }
}

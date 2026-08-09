import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../app/theme/app_colors.dart';
import '../../auth/domain/auth_failure.dart';
import '../../auth/presentation/auth_controller.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  void _showPlaceholder(BuildContext context, String feature) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$feature will be implemented in a future PR.')),
    );
  }

  Future<void> _logout(BuildContext context, WidgetRef ref) async {
    try {
      await ref.read(authControllerProvider.notifier).logout();
    } on AuthFailure catch (failure) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(failure.message)));
    } catch (_) {
      if (!context.mounted) {
        return;
      }

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Something went wrong. Please try again.'),
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
          IconButton(
            key: const Key('home-logout-button'),
            tooltip: 'Logout',
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
                  ? 'Good to see you'
                  : 'Good to see you, $greetingTarget',
              key: const Key('home-greeting'),
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Your Mealio dashboard is ready for the first real features.',
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 28),
            _FeatureCard(
              key: const Key('pantry-card'),
              title: 'Pantry',
              description: 'Track ingredients available at home.',
              icon: Icons.kitchen_outlined,
              accentColor: AppColors.sage,
              onTap: () => _showPlaceholder(context, 'Pantry'),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('ai-recipe-card'),
              title: 'AI Recipe',
              description: 'Generate recipe ideas using your preferences.',
              icon: Icons.auto_awesome_rounded,
              accentColor: AppColors.peach,
              onTap: () => _showPlaceholder(context, 'AI Recipe'),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('meal-plan-card'),
              title: 'Meal Plan',
              description: 'Organise meals across your week.',
              icon: Icons.calendar_month_outlined,
              accentColor: const Color(0xFFB7C9E2),
              onTap: () => _showPlaceholder(context, 'Meal Plan'),
            ),
            const SizedBox(height: 14),
            _FeatureCard(
              key: const Key('shopping-list-card'),
              title: 'Shopping List',
              description: 'Prepare ingredients for your planned meals.',
              icon: Icons.shopping_basket_outlined,
              accentColor: const Color(0xFFD8C4E8),
              onTap: () => _showPlaceholder(context, 'Shopping List'),
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

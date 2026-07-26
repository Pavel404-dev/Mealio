import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/app/app.dart';

void main() {
  Widget createApp() {
    return const ProviderScope(child: MealioApp());
  }

  Future<void> openLoginScreen(WidgetTester tester) async {
    await tester.pumpWidget(createApp());

    expect(find.byKey(const Key('splash-screen')), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 900));
    await tester.pump();
  }

  Future<void> openHomeScreen(WidgetTester tester) async {
    await openLoginScreen(tester);

    await tester.tap(find.byKey(const Key('continue-home-button')));
    await tester.pumpAndSettle();
  }

  testWidgets('application starts on the Splash screen', (tester) async {
    await tester.pumpWidget(createApp());

    expect(find.byKey(const Key('splash-screen')), findsOneWidget);
    expect(find.text('Mealio'), findsOneWidget);

    // Complete the Splash timer so no timer remains pending after the test.
    await tester.pump(const Duration(milliseconds: 900));
    await tester.pump();
  });

  testWidgets('Splash navigates to Login', (tester) async {
    await openLoginScreen(tester);

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('login-email-field')), findsOneWidget);
    expect(find.byKey(const Key('login-password-field')), findsOneWidget);
  });

  testWidgets('Continue to Home opens the Home screen', (tester) async {
    await openHomeScreen(tester);

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
  });

  testWidgets('Home displays the main feature cards', (tester) async {
    await openHomeScreen(tester);

    expect(find.text('Pantry'), findsOneWidget);
    expect(find.text('AI Recipe'), findsOneWidget);
    expect(find.text('Meal Plan'), findsOneWidget);
    expect(find.text('Shopping List'), findsOneWidget);
  });

  testWidgets('Home can return to Login', (tester) async {
    await openHomeScreen(tester);

    await tester.tap(find.byKey(const Key('home-login-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  });
}

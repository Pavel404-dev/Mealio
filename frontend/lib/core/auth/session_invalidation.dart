import 'package:flutter_riverpod/flutter_riverpod.dart';

final sessionInvalidationProvider =
    NotifierProvider<SessionInvalidationNotifier, int>(
      SessionInvalidationNotifier.new,
    );

class SessionInvalidationNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void invalidate() {
    state++;
  }
}

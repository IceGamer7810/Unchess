import 'package:flutter_test/flutter_test.dart';
import 'package:unchess_client_desktop/src/app.dart';

void main() {
  testWidgets('desktop app shell renders', (tester) async {
    await tester.pumpWidget(const UnchessDesktopApp());

    expect(find.text('Unchess Desktop'), findsOneWidget);
  });
}


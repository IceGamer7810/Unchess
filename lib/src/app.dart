import 'package:flutter/material.dart';

import 'features/home/presentation/home_screen.dart';
import 'theme/app_theme.dart';

class UnchessDesktopApp extends StatelessWidget {
  const UnchessDesktopApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Unchess Desktop',
      debugShowCheckedModeBanner: false,
      theme: buildUnchessTheme(),
      home: const HomeScreen(),
    );
  }
}


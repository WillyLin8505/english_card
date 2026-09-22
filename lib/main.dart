import 'package:flutter/material.dart';
import 'screens/home_screen.dart';

void main() {
  runApp(const EnglishCardApp());
}

class EnglishCardApp extends StatelessWidget {
  const EnglishCardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '拍照學英文',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          centerTitle: true,
        ),
      ),
      home: const HomeScreen(),
    );
  }
}

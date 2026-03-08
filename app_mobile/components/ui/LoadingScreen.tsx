import { ActivityIndicator, View, StyleSheet } from 'react-native';
import { useThemeColor } from '@/hooks/use-theme-color';

export function LoadingScreen() {
  const bg = useThemeColor({}, 'background');
  const tint = useThemeColor({}, 'primary');

  return (
    <View style={[styles.container, { backgroundColor: bg }]}>
      <ActivityIndicator size="large" color={tint} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});

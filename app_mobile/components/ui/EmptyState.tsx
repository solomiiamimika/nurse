import { View, Text, StyleSheet } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useThemeColor } from '@/hooks/use-theme-color';

interface EmptyStateProps {
  icon?: string;
  title: string;
  subtitle?: string;
}

export function EmptyState({ icon = 'inbox', title, subtitle }: EmptyStateProps) {
  const muted = useThemeColor({}, 'muted');

  return (
    <View style={styles.container}>
      <MaterialIcons name={icon as any} size={48} color={muted} />
      <Text style={[styles.title, { color: muted }]}>{title}</Text>
      {subtitle && <Text style={[styles.subtitle, { color: muted }]}>{subtitle}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 40 },
  title: { fontSize: 18, fontWeight: '600', marginTop: 12, textAlign: 'center' },
  subtitle: { fontSize: 14, marginTop: 6, textAlign: 'center' },
});

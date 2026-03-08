import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Image,
  Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '@/contexts/AuthContext';
import api from '../src/api/api';

interface PortfolioItem {
  filename: string;
  url: string;
}

const SCREEN_WIDTH = Dimensions.get('window').width;
const ITEM_GAP = 12;
const PADDING_H = 20;
const ITEM_WIDTH = (SCREEN_WIDTH - PADDING_H * 2 - ITEM_GAP) / 2;

export default function PortfolioScreen() {
  const { user } = useAuth();

  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const fetchPortfolio = async () => {
    setLoading(true);
    try {
      const res = await api.get('/provider/profile');
      const portfolio = res.data?.portfolio || [];
      // Portfolio might come as array of filenames or objects
      const mapped: PortfolioItem[] = portfolio.map((item: any) => {
        if (typeof item === 'string') {
          return {
            filename: item,
            url: `https://human-me.com/static/uploads/portfolio/${item}`,
          };
        }
        return {
          filename: item.filename || item.name,
          url: item.url || `https://human-me.com/static/uploads/portfolio/${item.filename || item.name}`,
        };
      });
      setItems(mapped);
    } catch (err) {
      console.error('Failed to fetch portfolio:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddPhoto = async () => {
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        quality: 0.8,
      });

      if (result.canceled || !result.assets?.[0]) return;

      const asset = result.assets[0];
      setUploading(true);

      const formData = new FormData();
      formData.append('file', {
        uri: asset.uri,
        name: asset.fileName || 'photo.jpg',
        type: asset.mimeType || 'image/jpeg',
      } as any);

      const res = await api.post('/provider/portfolio/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      // Refetch portfolio after upload
      await fetchPortfolio();
      Alert.alert('Success', 'Photo uploaded successfully');
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to upload photo';
      Alert.alert('Error', msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDeletePhoto = (filename: string) => {
    Alert.alert(
      'Delete Photo',
      'Are you sure you want to delete this photo?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await api.post('/provider/portfolio/delete', { filename });
              await fetchPortfolio();
              Alert.alert('Success', 'Photo deleted');
            } catch (err: any) {
              const msg = err.response?.data?.msg || 'Failed to delete photo';
              Alert.alert('Error', msg);
            }
          },
        },
      ]
    );
  };

  const renderItem = ({ item }: { item: PortfolioItem }) => (
    <View style={styles.gridItem}>
      <Image source={{ uri: item.url }} style={styles.image} resizeMode="cover" />
      <TouchableOpacity
        style={styles.deleteOverlay}
        onPress={() => handleDeletePhoto(item.filename)}
        activeOpacity={0.7}
      >
        <Text style={styles.deleteIcon}>&#10005;</Text>
      </TouchableOpacity>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: 'Portfolio' }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: true, title: 'Portfolio' }} />

      <FlatList
        data={items}
        keyExtractor={(item) => item.filename}
        renderItem={renderItem}
        numColumns={2}
        columnWrapperStyle={styles.row}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>No photos yet</Text>
            <Text style={styles.emptySubtitle}>
              Add photos to showcase your work to clients
            </Text>
          </View>
        }
      />

      {/* Add Photo Button */}
      <TouchableOpacity
        style={styles.fab}
        onPress={handleAddPhoto}
        disabled={uploading}
        activeOpacity={0.8}
      >
        {uploading ? (
          <ActivityIndicator size="small" color="#fff" />
        ) : (
          <Text style={styles.fabText}>+ Add Photo</Text>
        )}
      </TouchableOpacity>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
  },
  listContent: {
    paddingHorizontal: PADDING_H,
    paddingBottom: 100,
    paddingTop: 8,
  },
  row: {
    gap: ITEM_GAP,
    marginBottom: ITEM_GAP,
  },
  gridItem: {
    width: ITEM_WIDTH,
    height: ITEM_WIDTH,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#e5e7eb',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  deleteOverlay: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  deleteIcon: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: 60,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 8,
  },
  emptySubtitle: {
    fontSize: 14,
    color: '#6b7280',
    textAlign: 'center',
  },
  fab: {
    position: 'absolute',
    bottom: 30,
    alignSelf: 'center',
    backgroundColor: '#3f4a36',
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderRadius: 25,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 5,
  },
  fabText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});

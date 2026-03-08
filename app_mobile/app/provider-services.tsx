import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ActivityIndicator,
  Alert,
  Modal,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack } from 'expo-router';
import { useAuth } from '@/contexts/AuthContext';
import { Card } from '@/components/ui/Card';
import api from '../src/api/api';

interface Service {
  id: number;
  name: string;
  price: number;
  duration: number;
  description: string | null;
  tags?: string;
}

const POPULAR_TAGS = ['Home Care', 'Elderly', 'Childcare', 'Massage', 'Cleaning'];

export default function ProviderServicesScreen() {
  const { user } = useAuth();

  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  // Edit state
  const [editName, setEditName] = useState('');
  const [editPrice, setEditPrice] = useState('');
  const [editDuration, setEditDuration] = useState('');
  const [editDescription, setEditDescription] = useState('');

  // Add form state
  const [newName, setNewName] = useState('');
  const [newPrice, setNewPrice] = useState('');
  const [newDuration, setNewDuration] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchServices();
  }, []);

  const fetchServices = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/client/get_provider_services?provider_id=${user?.id}`);
      setServices(res.data?.services || res.data || []);
    } catch (err) {
      console.error('Failed to fetch services:', err);
    } finally {
      setLoading(false);
    }
  };

  const startEditing = (service: Service) => {
    setEditingId(service.id);
    setEditName(service.name);
    setEditPrice(String(service.price));
    setEditDuration(String(service.duration));
    setEditDescription(service.description || '');
  };

  const cancelEditing = () => {
    setEditingId(null);
  };

  const handleSaveEdit = async (serviceId: number) => {
    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('action', 'edit');
      formData.append('service_id', String(serviceId));
      formData.append('name', editName);
      formData.append('price', editPrice);
      formData.append('duration', editDuration);
      formData.append('description', editDescription);

      await api.post('/provider/services', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setEditingId(null);
      await fetchServices();
      Alert.alert('Success', 'Service updated');
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to update service';
      Alert.alert('Error', msg);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = (serviceId: number) => {
    Alert.alert(
      'Delete Service',
      'Are you sure you want to delete this service?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              const formData = new FormData();
              formData.append('action', 'remove');
              formData.append('service_id', String(serviceId));

              await api.post('/provider/services', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
              });

              await fetchServices();
              Alert.alert('Success', 'Service deleted');
            } catch (err: any) {
              const msg = err.response?.data?.msg || 'Failed to delete service';
              Alert.alert('Error', msg);
            }
          },
        },
      ]
    );
  };

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const handleAddService = async () => {
    if (!newName.trim() || !newPrice.trim() || !newDuration.trim()) {
      Alert.alert('Error', 'Please fill in name, price, and duration');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('action', 'add');
      formData.append('name', newName.trim());
      formData.append('price', newPrice);
      formData.append('duration', newDuration);
      formData.append('description', newDescription.trim());
      formData.append('tags', selectedTags.join(','));

      await api.post('/provider/services', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setShowAddModal(false);
      resetAddForm();
      await fetchServices();
      Alert.alert('Success', 'Service added');
    } catch (err: any) {
      const msg = err.response?.data?.msg || 'Failed to add service';
      Alert.alert('Error', msg);
    } finally {
      setSaving(false);
    }
  };

  const resetAddForm = () => {
    setNewName('');
    setNewPrice('');
    setNewDuration('');
    setNewDescription('');
    setSelectedTags([]);
  };

  const renderService = ({ item }: { item: Service }) => {
    const isEditing = editingId === item.id;

    if (isEditing) {
      return (
        <Card style={styles.serviceCard}>
          <TextInput
            style={styles.editInput}
            value={editName}
            onChangeText={setEditName}
            placeholder="Service name"
          />
          <View style={styles.editRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.editLabel}>Price (\u20AC)</Text>
              <TextInput
                style={styles.editInput}
                value={editPrice}
                onChangeText={setEditPrice}
                keyboardType="numeric"
                placeholder="Price"
              />
            </View>
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={styles.editLabel}>Duration (min)</Text>
              <TextInput
                style={styles.editInput}
                value={editDuration}
                onChangeText={setEditDuration}
                keyboardType="numeric"
                placeholder="Duration"
              />
            </View>
          </View>
          <TextInput
            style={[styles.editInput, styles.textArea]}
            value={editDescription}
            onChangeText={setEditDescription}
            placeholder="Description"
            multiline
            numberOfLines={3}
            textAlignVertical="top"
          />
          <View style={styles.editActions}>
            <TouchableOpacity
              style={styles.cancelBtn}
              onPress={cancelEditing}
            >
              <Text style={styles.cancelBtnText}>Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.saveEditBtn}
              onPress={() => handleSaveEdit(item.id)}
              disabled={saving}
            >
              {saving ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={styles.saveEditBtnText}>Save</Text>
              )}
            </TouchableOpacity>
          </View>
        </Card>
      );
    }

    return (
      <Card style={styles.serviceCard}>
        <View style={styles.serviceHeader}>
          <Text style={styles.serviceName}>{item.name}</Text>
          <Text style={styles.servicePrice}>{'\u20AC'}{item.price}</Text>
        </View>
        <Text style={styles.serviceDuration}>{item.duration} min</Text>
        {item.description ? (
          <Text style={styles.serviceDescription}>{item.description}</Text>
        ) : null}
        <View style={styles.serviceActions}>
          <TouchableOpacity
            style={styles.editBtn}
            onPress={() => startEditing(item)}
          >
            <Text style={styles.editBtnText}>Edit</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.deleteBtn}
            onPress={() => handleDelete(item.id)}
          >
            <Text style={styles.deleteBtnText}>Delete</Text>
          </TouchableOpacity>
        </View>
      </Card>
    );
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.centered}>
        <Stack.Screen options={{ headerShown: true, title: 'My Services' }} />
        <ActivityIndicator size="large" color="#3f4a36" />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={['top']}>
      <Stack.Screen options={{ headerShown: true, title: 'My Services' }} />

      <FlatList
        data={services}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderService}
        contentContainerStyle={styles.listContent}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyTitle}>No services yet</Text>
            <Text style={styles.emptySubtitle}>Add your first service to start receiving bookings</Text>
          </View>
        }
      />

      {/* Add Service FAB */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() => setShowAddModal(true)}
        activeOpacity={0.8}
      >
        <Text style={styles.fabText}>+ Add Service</Text>
      </TouchableOpacity>

      {/* Add Service Modal */}
      <Modal
        visible={showAddModal}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setShowAddModal(false)}
      >
        <SafeAreaView style={styles.modalContainer}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={{ flex: 1 }}
          >
            <ScrollView contentContainerStyle={styles.modalContent} showsVerticalScrollIndicator={false}>
              <View style={styles.modalHeader}>
                <Text style={styles.modalTitle}>Add New Service</Text>
                <TouchableOpacity onPress={() => setShowAddModal(false)}>
                  <Text style={styles.modalClose}>Cancel</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.inputLabel}>Service Name</Text>
              <TextInput
                style={styles.input}
                value={newName}
                onChangeText={setNewName}
                placeholder="e.g. Home Care Visit"
              />

              <View style={styles.editRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.inputLabel}>Price ({'\u20AC'})</Text>
                  <TextInput
                    style={styles.input}
                    value={newPrice}
                    onChangeText={setNewPrice}
                    keyboardType="numeric"
                    placeholder="25"
                  />
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.inputLabel}>Duration (min)</Text>
                  <TextInput
                    style={styles.input}
                    value={newDuration}
                    onChangeText={setNewDuration}
                    keyboardType="numeric"
                    placeholder="60"
                  />
                </View>
              </View>

              <Text style={styles.inputLabel}>Description</Text>
              <TextInput
                style={[styles.input, styles.textArea]}
                value={newDescription}
                onChangeText={setNewDescription}
                placeholder="Describe your service..."
                multiline
                numberOfLines={4}
                textAlignVertical="top"
              />

              <Text style={styles.inputLabel}>Tags</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tagsScroll}>
                <View style={styles.tagsRow}>
                  {POPULAR_TAGS.map((tag) => (
                    <TouchableOpacity
                      key={tag}
                      style={[
                        styles.tagChip,
                        selectedTags.includes(tag) && styles.tagChipActive,
                      ]}
                      onPress={() => toggleTag(tag)}
                    >
                      <Text
                        style={[
                          styles.tagChipText,
                          selectedTags.includes(tag) && styles.tagChipTextActive,
                        ]}
                      >
                        {tag}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>

              <TouchableOpacity
                style={styles.addBtn}
                onPress={handleAddService}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator size="small" color="#fff" />
                ) : (
                  <Text style={styles.addBtnText}>Save Service</Text>
                )}
              </TouchableOpacity>
            </ScrollView>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </Modal>
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
    paddingHorizontal: 20,
    paddingBottom: 100,
    paddingTop: 8,
  },
  serviceCard: {
    marginBottom: 12,
  },
  serviceHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  serviceName: {
    fontSize: 16,
    fontWeight: '600',
    color: '#1f2937',
    flex: 1,
  },
  servicePrice: {
    fontSize: 18,
    fontWeight: '700',
    color: '#3f4a36',
  },
  serviceDuration: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 4,
  },
  serviceDescription: {
    fontSize: 14,
    color: '#374151',
    marginTop: 4,
  },
  serviceActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#f3f4f6',
  },
  editBtn: {
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#f0f1ee',
  },
  editBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3f4a36',
  },
  deleteBtn: {
    paddingVertical: 8,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#fef2f2',
  },
  deleteBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#ef4444',
  },
  editInput: {
    height: 44,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 10,
    paddingHorizontal: 12,
    borderRadius: 8,
    backgroundColor: '#fff',
    fontSize: 15,
  },
  editRow: {
    flexDirection: 'row',
  },
  editLabel: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 4,
  },
  textArea: {
    height: 80,
    paddingTop: 10,
  },
  editActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 4,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#e5e7eb',
  },
  cancelBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#374151',
  },
  saveEditBtn: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#3f4a36',
  },
  saveEditBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
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
  // Modal styles
  modalContainer: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  modalContent: {
    paddingHorizontal: 20,
    paddingBottom: 40,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 16,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1f2937',
  },
  modalClose: {
    fontSize: 16,
    color: '#3f4a36',
    fontWeight: '600',
  },
  inputLabel: {
    marginBottom: 8,
    color: '#333',
    fontWeight: '600',
    fontSize: 14,
  },
  input: {
    height: 50,
    borderColor: '#e1e1e1',
    borderWidth: 1,
    marginBottom: 16,
    paddingHorizontal: 15,
    borderRadius: 10,
    backgroundColor: '#fff',
    fontSize: 16,
  },
  tagsScroll: {
    marginBottom: 20,
  },
  tagsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  tagChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#d1d5db',
  },
  tagChipActive: {
    backgroundColor: '#3f4a36',
    borderColor: '#3f4a36',
  },
  tagChipText: {
    fontSize: 14,
    fontWeight: '500',
    color: '#6b7280',
  },
  tagChipTextActive: {
    color: '#fff',
  },
  addBtn: {
    backgroundColor: '#3f4a36',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginTop: 8,
  },
  addBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});

// Auth
export interface LoginResponse {
  access_token: string;
  user: { id: number; username: string; email: string; full_name: string; role: string; photo: string | null };
}

export interface RegisterResponse {
  msg: string;
  access_token: string;
  user: { id: number; username: string; role: string };
}

// Provider
export interface Provider {
  id: number;
  name: string;
  username: string;
  address: string | null;
  online: boolean;
  latitude: number | null;
  longitude: number | null;
  distance_km: number | null;
  services_count: number;
  service_names: string[];
  avg_rating: number | null;
  review_count: number;
  photo: string | null;
  verified: boolean;
  service_tags: string[];
}

export interface ProviderService {
  id: number;
  name: string;
  price: number;
  duration: number;
  description: string | null;
}

export interface CancellationPolicyInfo {
  has_policy: boolean;
  free_cancel_hours?: number;
  late_cancel_fee_percent?: number;
  no_show_client_fee_percent?: number;
  description: string;
}

// Appointments
export interface AppointmentEvent {
  id: number;
  title: string;
  start: string;
  end: string;
  color: string;
  extendedProps: {
    status: string;
    notes: string;
    provider_name?: string;
    client_name?: string;
    service_name: string;
    amount: string;
    appointment_id: number;
  };
}

export interface ClientRequest {
  id: number;
  service_name: string;
  status: string;
  appointment_start_time: string;
  created_appo: string;
  notes: string;
  payment: number;
  address: string;
  district: string;
  service_tags: string;
  offers: OfferInfo[];
  accepted_provider: AcceptedProviderInfo | null;
}

export interface OfferInfo {
  offer_id: number;
  provider_id: number;
  provider_name: string;
  proposed_price: number;
  counter_price: number | null;
  status: string;
  last_action_by: string;
}

export interface AcceptedProviderInfo {
  provider_id: number;
  provider_name: string;
  price: number;
}

// Chat
export interface Conversation {
  user_id: number;
  name: string;
  photo: string | null;
  last_message: string;
  last_message_type: string;
  timestamp: string;
  unread: number;
}

export interface ChatMessage {
  id: number;
  sender_id: number;
  text: string;
  message_type: string;
  file_url: string | null;
  file_name: string | null;
  file_size: number | null;
  timestamp: string;
  is_read: boolean;
  proposal_status: string | null;
}

// Reviews
export interface Review {
  id: number;
  patient_id: number;
  patient_name: string;
  provider_id: number;
  rating: number;
  comment: string | null;
  response_text: string | null;
  created_at: string;
}

// Stats
export interface PlatformStats {
  provider_count: number;
  completed_tasks: number;
  avg_rating: number;
}

export interface ProviderStats {
  accepted: number;
  completed: number;
  upcoming: number;
  rating: number;
}

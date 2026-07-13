package entities

type College struct {
	ID           string        `json:"id" bson:"_id,omitempty"`
	State        string        `json:"state" bson:"state"`
	Name         string        `json:"name" bson:"name"`
	AddressLine1 string        `json:"address_line1" bson:"address_line1"`
	AddressLine2 string        `json:"address_line2" bson:"address_line2"`
	City         string        `json:"city" bson:"city"`
	District     string        `json:"district" bson:"district"`
	PinCode      string        `json:"pin_code" bson:"pin_code"`
	Website      string        `json:"website" bson:"website"`
	PhoneNumbers string        `json:"phone_numbers" bson:"phone_numbers"`
	Emails       string        `json:"emails" bson:"emails"`
	Professors   []Professor   `json:"professors" bson:"professors"`
}

type Professor struct {
	Name  string `json:"name" bson:"name"`
	Email string `json:"email" bson:"email"`
	Phone string `json:"phone" bson:"phone"`
}

type User struct {
	ID        string   `json:"id" bson:"_id,omitempty"`
	Name      string   `json:"name" bson:"name"`
	Email     string   `json:"email" bson:"email"`
	Password  string   `json:"-" bson:"password"`
	Token     string   `json:"token,omitempty" bson:"token,omitempty"`
	Favorites []string `json:"favorites,omitempty" bson:"favorites,omitempty"`
}

type SignupRequest struct {
	Name     string `json:"name"`
	Email    string `json:"email"`
	Password string `json:"password"`
}

type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

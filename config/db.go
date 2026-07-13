package config

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

var (
	MongoCollection    *mongo.Collection
	UserCollection     *mongo.Collection
	FavoriteCollection *mongo.Collection
)

func Connect() error {
	uri := os.Getenv("MONGODB_URI")
	if uri == "" {
		uri = "mongodb+srv://anchal:anchal@anchal.hospij1.mongodb.net/dbcolleges?appName=anchal"
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		return fmt.Errorf("mongo connect error: %v", err)
	}

	if err := client.Ping(ctx, nil); err != nil {
		return fmt.Errorf("mongo ping error: %v", err)
	}

	MongoCollection = client.Database("dbcolleges").Collection("colleges")
	UserCollection = client.Database("dbcolleges").Collection("users")
	FavoriteCollection = client.Database("dbcolleges").Collection("favorites")

	// Verify data exists
	count, err := MongoCollection.CountDocuments(ctx, bson.M{})
	if err != nil {
		return fmt.Errorf("mongo count error: %v", err)
	}

	log.Printf("MongoDB connected — %d colleges found", count)
	return nil
}

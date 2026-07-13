package handlers

import (
	"context"
	"net/http"
	"strings"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/entities"
	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type UserSummary struct {
	Name        string `json:"name"`
	Email       string `json:"email"`
	MarkedCount int    `json:"markedCount"`
}

func (h *APIhandler) ListUsers(c *fiber.Ctx) error {
	ctx := context.Background()

	cursor, err := config.UserCollection.Find(ctx, bson.M{}, options.Find().SetProjection(bson.M{"name": 1, "email": 1, "favorites": 1}))
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to fetch users"})
	}
	defer cursor.Close(ctx)

	var users []entities.User
	if err := cursor.All(ctx, &users); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to decode users"})
	}

	summaries := make([]UserSummary, 0, len(users))
	for _, u := range users {
		summaries = append(summaries, UserSummary{
			Name:        u.Name,
			Email:       u.Email,
			MarkedCount: len(u.Favorites),
		})
	}

	return c.Status(http.StatusOK).JSON(fiber.Map{"users": summaries})
}

func (h *APIhandler) GetUserColleges(c *fiber.Ctx) error {
	email := strings.ReplaceAll(c.Params("email"), "%20", " ")
	ctx := context.Background()

	var user entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"email": email}).Decode(&user); err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"error": "User not found"})
	}

	if len(user.Favorites) == 0 {
		return c.Status(http.StatusOK).JSON(fiber.Map{"colleges": []entities.College{}, "user": UserSummary{Name: user.Name, Email: user.Email, MarkedCount: 0}})
	}

	// Convert string IDs to ObjectIDs for MongoDB query
	objIDs := []primitive.ObjectID{}
	for _, id := range user.Favorites {
		if len(id) == 24 {
			if oid, err := primitive.ObjectIDFromHex(id); err == nil {
				objIDs = append(objIDs, oid)
			}
		}
	}

	if len(objIDs) == 0 {
		return c.Status(http.StatusOK).JSON(fiber.Map{"colleges": []entities.College{}, "user": UserSummary{Name: user.Name, Email: user.Email, MarkedCount: len(user.Favorites)}})
	}

	cursor, err := config.MongoCollection.Find(ctx, bson.M{"_id": bson.M{"$in": objIDs}})
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to fetch colleges"})
	}
	defer cursor.Close(ctx)

	colleges := []entities.College{}
	if err := cursor.All(ctx, &colleges); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to decode colleges"})
	}

	return c.Status(http.StatusOK).JSON(fiber.Map{
		"user":     UserSummary{Name: user.Name, Email: user.Email, MarkedCount: len(user.Favorites)},
		"colleges": colleges,
	})
}

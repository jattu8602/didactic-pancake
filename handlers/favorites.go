package handlers

import (
	"context"
	"net/http"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/entities"
	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
)

func (h *APIhandler) ToggleFavorite(c *fiber.Ctx) error {
	token := extractToken(c)
	if token == "" {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "No auth token"})
	}

	var body struct {
		CollegeID string `json:"collegeId"`
	}
	if err := c.BodyParser(&body); err != nil || body.CollegeID == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"error": "collegeId is required"})
	}

	ctx := context.Background()

	var user entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"token": token}).Decode(&user); err != nil {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid token"})
	}

	filter := bson.M{"email": user.Email}
	found := false
	for _, fid := range user.Favorites {
		if fid == body.CollegeID {
			found = true
			break
		}
	}

	if found {
		config.UserCollection.UpdateOne(ctx, filter, bson.M{"$pull": bson.M{"favorites": body.CollegeID}})
	} else {
		config.UserCollection.UpdateOne(ctx, filter, bson.M{"$push": bson.M{"favorites": body.CollegeID}})
	}

	return c.Status(http.StatusOK).JSON(fiber.Map{"favorited": !found})
}

func (h *APIhandler) GetFavorites(c *fiber.Ctx) error {
	token := extractToken(c)
	if token == "" {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "No auth token"})
	}

	ctx := context.Background()
	var user entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"token": token}).Decode(&user); err != nil {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid token"})
	}

	return c.Status(http.StatusOK).JSON(fiber.Map{"favorites": user.Favorites})
}

package handlers

import (
	"context"
	"net/http"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/entities"
	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type MarkedByUser struct {
	Name  string `json:"name" bson:"name"`
	Email string `json:"email" bson:"email"`
}

type CollegeMark struct {
	CollegeID string         `json:"collegeId" bson:"collegeId"`
	MarkedBy  []MarkedByUser `json:"markedBy" bson:"markedBy"`
}

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

	// Toggle personal favorite
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

	// Toggle global college mark
	markFilter := bson.M{"collegeId": body.CollegeID}
	userEntry := MarkedByUser{Name: user.Name, Email: user.Email}

	if found {
		config.CollegeMarksCollection.UpdateOne(ctx, markFilter, bson.M{"$pull": bson.M{"markedBy": userEntry}})
	} else {
		update := bson.M{
			"$push": bson.M{"markedBy": userEntry},
			"$setOnInsert": bson.M{"collegeId": body.CollegeID},
		}
		opts := options.Update().SetUpsert(true)
		config.CollegeMarksCollection.UpdateOne(ctx, markFilter, update, opts)
	}

	// Clean up empty marks
	config.CollegeMarksCollection.DeleteOne(ctx, bson.M{"collegeId": body.CollegeID, "markedBy": bson.M{"$size": 0}})

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

func (h *APIhandler) GetAllCollegeMarks(c *fiber.Ctx) error {
	ctx := context.Background()

	cursor, err := config.CollegeMarksCollection.Find(ctx, bson.M{})
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to fetch marks"})
	}
	defer cursor.Close(ctx)

	var marks []CollegeMark
	if err := cursor.All(ctx, &marks); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to decode marks"})
	}

	return c.Status(http.StatusOK).JSON(fiber.Map{"marks": marks})
}

package handlers

import (
	"context"
	"net/http"
	"strconv"
	"strings"
	"time"

	"golang.org/x/time/rate"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/entities"
	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type APIhandler struct {
	rateLimiter *rate.Limiter
}

func NewAPIhandler() *APIhandler {
	return &APIhandler{
		rateLimiter: rate.NewLimiter(rate.Every(time.Second)*3, 10),
	}
}

func (h *APIhandler) GetAllStates(c *fiber.Ctx) error {
	if err := h.rateLimiter.Wait(c.Context()); err != nil {
		return err
	}
	ctx := context.Background()
	states, err := config.MongoCollection.Distinct(ctx, "state", bson.M{})
	if err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "States not found"})
	}
	return c.Status(http.StatusOK).JSON(states)
}

func (h *APIhandler) GetDistrictsByState(c *fiber.Ctx) error {
	if err := h.rateLimiter.Wait(c.Context()); err != nil {
		return err
	}
	state := strings.ReplaceAll(c.Params("state"), "%20", " ")
	state = strings.Title(strings.ToLower(state))
	ctx := context.Background()
	districts, err := config.MongoCollection.Distinct(ctx, "district", bson.M{"state": state})
	if err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "Districts not found"})
	}
	return c.Status(http.StatusOK).JSON(districts)
}

func (h *APIhandler) GetAllCollegesInState(c *fiber.Ctx) error {
	if err := h.rateLimiter.Wait(c.Context()); err != nil {
		return err
	}
	state := strings.ReplaceAll(c.Params("state"), "%20", " ")
	state = strings.Title(strings.ToLower(state))
	page, _ := strconv.Atoi(c.Query("page", "1"))
	limit, _ := strconv.Atoi(c.Query("limit", "10"))
	search := c.Query("search")

	if page < 1 {
		page = 1
	}

	ctx := context.Background()
	filter := bson.M{"state": state}

	if search != "" {
		filter["name"] = bson.M{"$regex": search, "$options": "i"}
	}

	total, _ := config.MongoCollection.CountDocuments(ctx, filter)

	findOpts := options.Find().
		SetSort(bson.M{"name": 1}).
		SetSkip(int64((page - 1) * limit)).
		SetLimit(int64(limit))

	cursor, err := config.MongoCollection.Find(ctx, filter, findOpts)
	if err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "College not found"})
	}
	defer cursor.Close(ctx)

	var colleges []entities.College
	if err := cursor.All(ctx, &colleges); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"message": "Error decoding colleges"})
	}

	totalPages := int(total) / limit
	return c.Status(http.StatusOK).JSON(fiber.Map{
		"count":       total,
		"currentPage": page,
		"pages":       totalPages + 1,
		"colleges":    colleges,
	})
}

func (h *APIhandler) GetAllCollegesInDistrict(c *fiber.Ctx) error {
	if err := h.rateLimiter.Wait(c.Context()); err != nil {
		return err
	}
	state := strings.ReplaceAll(c.Params("state"), "%20", " ")
	state = strings.Title(strings.ToLower(state))
	district := strings.ReplaceAll(c.Params("district"), "%20", " ")
	district = strings.Title(strings.ToLower(district))
	page, _ := strconv.Atoi(c.Query("page", "1"))
	limit, _ := strconv.Atoi(c.Query("limit", "10"))
	search := c.Query("search")

	if page < 1 {
		page = 1
	}

	ctx := context.Background()
	filter := bson.M{"state": state, "district": district}

	if search != "" {
		filter["name"] = bson.M{"$regex": search, "$options": "i"}
	}

	total, _ := config.MongoCollection.CountDocuments(ctx, filter)

	findOpts := options.Find().
		SetSort(bson.M{"name": 1}).
		SetSkip(int64((page - 1) * limit)).
		SetLimit(int64(limit))

	cursor, err := config.MongoCollection.Find(ctx, filter, findOpts)
	if err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "College not found"})
	}
	defer cursor.Close(ctx)

	var colleges []entities.College
	if err := cursor.All(ctx, &colleges); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"message": "Error decoding colleges"})
	}

	totalPages := int(total) / limit
	return c.Status(http.StatusOK).JSON(fiber.Map{
		"count":       total,
		"currentPage": page,
		"pages":       totalPages + 1,
		"colleges":    colleges,
	})
}

func (h *APIhandler) ListColleges(c *fiber.Ctx) error {
	ctx := context.Background()
	state := c.Query("state")
	search := c.Query("search")
	limitStr := c.Query("limit", "500")

	limit, err := strconv.Atoi(limitStr)
	if err != nil || limit < 1 {
		limit = 500
	}

	filter := bson.M{}
	if state != "" {
		filter["state"] = bson.M{"$regex": state, "$options": "i"}
	}
	if search != "" {
		filter["name"] = bson.M{"$regex": search, "$options": "i"}
	}

	findOpts := options.Find().
		SetSort(bson.M{"name": 1}).
		SetLimit(int64(limit))

	cursor, err := config.MongoCollection.Find(ctx, filter, findOpts)
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to fetch colleges"})
	}
	defer cursor.Close(ctx)

	var colleges []entities.College
	if err := cursor.All(ctx, &colleges); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to decode colleges"})
	}

	return c.JSON(fiber.Map{
		"total":    len(colleges),
		"colleges": colleges,
	})
}

func (h *APIhandler) SearchCollege(c *fiber.Ctx) error {
	if err := h.rateLimiter.Wait(c.Context()); err != nil {
		return err
	}
	search := c.Query("search")
	page, _ := strconv.Atoi(c.Query("page", "1"))
	limit, _ := strconv.Atoi(c.Query("limit", "10"))

	if page < 1 {
		page = 1
	}

	ctx := context.Background()
	filter := bson.M{"name": bson.M{"$regex": search, "$options": "i"}}

	total, _ := config.MongoCollection.CountDocuments(ctx, filter)

	findOpts := options.Find().
		SetSort(bson.M{"name": 1}).
		SetSkip(int64((page - 1) * limit)).
		SetLimit(int64(limit))

	cursor, err := config.MongoCollection.Find(ctx, filter, findOpts)
	if err != nil {
		return c.Status(http.StatusNotFound).JSON(fiber.Map{"message": "College not found"})
	}
	defer cursor.Close(ctx)

	var colleges []entities.College
	if err := cursor.All(ctx, &colleges); err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"message": "Error decoding colleges"})
	}

	totalPages := int(total) / limit
	return c.Status(http.StatusOK).JSON(fiber.Map{
		"count":       total,
		"currentPage": page,
		"pages":       totalPages + 1,
		"colleges":    colleges,
	})
}

package handlers

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/entities"
	"github.com/gofiber/fiber/v2"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"golang.org/x/crypto/bcrypt"
)

func generateToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}

func (h *APIhandler) Signup(c *fiber.Ctx) error {
	var req entities.SignupRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"error": "Invalid request body"})
	}
	if req.Name == "" || req.Email == "" || req.Password == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"error": "Name, email, and password are required"})
	}

	ctx := context.Background()

	var existing entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"email": req.Email}).Decode(&existing); err == nil {
		return c.Status(http.StatusConflict).JSON(fiber.Map{"error": "Email already registered"})
	}

	hash, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to hash password"})
	}

	token, err := generateToken()
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to generate token"})
	}

	user := entities.User{
		Name:     req.Name,
		Email:    req.Email,
		Password: string(hash),
		Token:    token,
	}

	result, err := config.UserCollection.InsertOne(ctx, user)
	if err != nil {
		return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to create user"})
	}

	user.ID = result.InsertedID.(primitive.ObjectID).Hex()
	user.Password = ""

	return c.Status(http.StatusCreated).JSON(fiber.Map{
		"user":  user,
		"token": token,
	})
}

func (h *APIhandler) Login(c *fiber.Ctx) error {
	var req entities.LoginRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"error": "Invalid request body"})
	}
	if req.Email == "" || req.Password == "" {
		return c.Status(http.StatusBadRequest).JSON(fiber.Map{"error": "Email and password are required"})
	}

	ctx := context.Background()

	var user entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"email": req.Email}).Decode(&user); err != nil {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid email or password"})
	}

	if err := bcrypt.CompareHashAndPassword([]byte(user.Password), []byte(req.Password)); err != nil {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid email or password"})
	}

	token := user.Token
	if token == "" {
		var genErr error
		token, genErr = generateToken()
		if genErr != nil {
			return c.Status(http.StatusInternalServerError).JSON(fiber.Map{"error": "Failed to generate token"})
		}
		config.UserCollection.UpdateOne(ctx, bson.M{"email": req.Email}, bson.M{"$set": bson.M{"token": token}})
	}
	user.Token = token
	user.Password = ""

	return c.Status(http.StatusOK).JSON(fiber.Map{
		"user":  user,
		"token": token,
	})
}

func (h *APIhandler) GetMe(c *fiber.Ctx) error {
	token := extractToken(c)
	if token == "" {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "No auth token"})
	}

	ctx := context.Background()
	var user entities.User
	if err := config.UserCollection.FindOne(ctx, bson.M{"token": token}).Decode(&user); err != nil {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "Invalid token"})
	}

	user.Password = ""
	return c.Status(http.StatusOK).JSON(fiber.Map{"user": user})
}

func (h *APIhandler) Logout(c *fiber.Ctx) error {
	token := extractToken(c)
	if token == "" {
		return c.Status(http.StatusUnauthorized).JSON(fiber.Map{"error": "No auth token"})
	}

	ctx := context.Background()
	config.UserCollection.UpdateOne(ctx, bson.M{"token": token}, bson.M{"$set": bson.M{"token": ""}})
	return c.Status(http.StatusOK).JSON(fiber.Map{"message": "Logged out"})
}

func extractToken(c *fiber.Ctx) string {
	auth := c.Get("Authorization")
	if len(auth) > 7 && auth[:7] == "Bearer " {
		return auth[7:]
	}
	return c.Query("token")
}

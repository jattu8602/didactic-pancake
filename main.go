package main

import (
	"encoding/json"
	"log"
	"os"
	"strconv"
	"strings"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/handlers"
	"github.com/gofiber/fiber/v2"
)

type Professor struct {
	Name  string `json:"name"`
	Phone string `json:"phone"`
	Email string `json:"email"`
}

type College struct {
	ID           string      `json:"id"`
	State        string      `json:"state"`
	Name         string      `json:"name"`
	AddressLine1 string      `json:"address_line1"`
	AddressLine2 string      `json:"address_line2"`
	City         string      `json:"city"`
	District     string      `json:"district"`
	PinCode      string      `json:"pin_code"`
	Website      string      `json:"website"`
	PhoneNumbers string      `json:"phone_numbers"`
	Emails       string      `json:"emails"`
	Professors   []Professor `json:"professors"`
}

type CollegesData struct {
	Colleges []College `json:"colleges"`
}

func loadData() (CollegesData, error) {
	var data CollegesData
	file, err := os.ReadFile("./public/data/colleges.json")
	if err != nil {
		log.Println("Could not load colleges.json:", err)
		return data, err
	}
	if err := json.Unmarshal(file, &data); err != nil {
		log.Println("Error parsing colleges.json:", err)
		return data, err
	}
	return data, nil
}

func main() {
	app := fiber.New()

	app.Get("/", func(c *fiber.Ctx) error {
		return c.SendFile("./public/browse.html")
	})

	app.Static("/", "./public")

	// Live JSON Filter API for n8n / external automations
	app.Get("/api/colleges/live", func(c *fiber.Ctx) error {
		liveData, err := loadData()
		if err != nil {
			return c.Status(500).JSON(fiber.Map{"error": "Failed to load data"})
		}

		state := c.Query("state")
		district := c.Query("district")
		search := c.Query("search")
		hasEmail := c.Query("has_email") == "true"
		limitStr := c.Query("limit", "100")
		limit, err := strconv.Atoi(limitStr)
		if err != nil {
			limit = 100
		}

		var filtered []College

		for _, col := range liveData.Colleges {
			if state != "" && !strings.EqualFold(col.State, state) {
				continue
			}
			if district != "" && !strings.EqualFold(col.District, district) {
				continue
			}
			if search != "" && !strings.Contains(strings.ToLower(col.Name), strings.ToLower(search)) {
				continue
			}
			if hasEmail && col.Emails == "" {
				continue
			}
			
			filtered = append(filtered, col)
			if limit > 0 && len(filtered) >= limit {
				break
			}
		}

		return c.JSON(fiber.Map{
			"total":    len(filtered),
			"colleges": filtered,
		})
	})

	// Try connecting to DB – API routes only if DB is available
	handlerObj, err := tryConnectDB()
	if err == nil && handlerObj != nil {
		app.Get("colleges/", handlerObj.SearchCollege)
		app.Get("colleges/states", handlerObj.GetAllStates)
		app.Get("colleges/:state/districts", handlerObj.GetDistrictsByState)
		app.Get("colleges/:state", handlerObj.GetAllCollegesInState)
		app.Get("colleges/:state/:district", handlerObj.GetAllCollegesInDistrict)

		api := app.Group("/api")
		api.Post("/auth/signup", handlerObj.Signup)
		api.Post("/auth/login", handlerObj.Login)
		api.Get("/auth/me", handlerObj.GetMe)
		api.Post("/auth/logout", handlerObj.Logout)
		api.Post("/favorites/toggle", handlerObj.ToggleFavorite)
		api.Get("/favorites", handlerObj.GetFavorites)
		api.Get("/marks", handlerObj.GetAllCollegeMarks)
		api.Get("/users", handlerObj.ListUsers)
		api.Get("/users/:email/colleges", handlerObj.GetUserColleges)

		log.Println("Database connected – DB API routes enabled")
	} else {
		log.Println("Database not available – serving static files and live JSON API only")
	}

	log.Println("Server running. Browse at http://localhost:3000")
	log.Println("Live API ready at http://localhost:3000/api/colleges/live")
	log.Fatal(app.Listen(":3000"))
}

func tryConnectDB() (*handlers.APIhandler, error) {
	if err := config.Connect(); err != nil {
		return nil, err
	}
	return handlers.NewAPIhandler(), nil
}

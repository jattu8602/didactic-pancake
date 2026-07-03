package main

import (
	"log"

	"github.com/PriyanKishoreMS/colleges-list-api/config"
	"github.com/PriyanKishoreMS/colleges-list-api/handlers"
	"github.com/gofiber/fiber/v2"
)

func main() {
	app := fiber.New()

	app.Get("/", func(c *fiber.Ctx) error {
		return c.SendFile("./public/browse.html")
	})

	app.Static("/", "./public")

	// Try connecting to DB – API routes only if DB is available
	handlerObj, err := tryConnectDB()
	if err == nil && handlerObj != nil {
		app.Get("colleges/", handlerObj.SearchCollege)
		app.Get("colleges/states", handlerObj.GetAllStates)
		app.Get("colleges/:state/districts", handlerObj.GetDistrictsByState)
		app.Get("colleges/:state", handlerObj.GetAllCollegesInState)
		app.Get("colleges/:state/:district", handlerObj.GetAllCollegesInDistrict)
		log.Println("Database connected – API routes enabled")
	} else {
		log.Println("Database not available – serving static files only (browse + colleges.json)")
		log.Println("Visit http://localhost:3000 to browse colleges")
	}

	log.Fatal(app.Listen(":3000"))
}

func tryConnectDB() (*handlers.APIhandler, error) {
	if err := config.Connect(); err != nil {
		return nil, err
	}
	return handlers.NewAPIhandler(), nil
}
